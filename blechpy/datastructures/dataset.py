import pandas as pd
import datetime as dt
import pickle
import os
import shutil
import sys
import multiprocessing
import subprocess
from copy import deepcopy
from blechpy.utils import print_tools as pt, write_tools as wt
from blechpy.utils.decorators import Logger
from blechpy.analysis import palatability_analysis as pal_analysis, spike_sorting as ss, spike_analysis
from blechpy.plotting import palatability_plot as pal_plt, data_plot as datplt
from blechpy.utils import userIO
from blechpy import dio

class dataset(object):
    '''Stores information related to an intan recording directory, allows
    executing basic processing and analysis scripts, and stores parameters data
    for those analyses

    Parameters
    ----------
    file_dir : str (optional)
        absolute path to a recording directory, if left empty a filechooser
        will popup
    '''

    def __init__(self, file_dir=None):
        '''Initialize dataset object from file_dir, grabs basename from name of
        directory and initializes basic analysis parameters

        Parameters
        ----------
        file_dir : str (optional), file directory for intan recording data

        Throws
        ------
        ValueError
            if file_dir is not provided and no directory is chosen
            when prompted
        NotADirectoryError : if file_dir does not exist
        '''
        # Get file directory is not given
        if file_dir is None:
            file_dir = userIO.get_filedirs('Select recording directory', shell=shell)
            if file_dir is None:
                raise ValueError('Dataset cannot be initialized without a '
                                 'directory')

        if not os.path.isdir(file_dir):
            raise NotADirectoryError('Could not find folder %s' % file_dir)

        # Get basename of dataset from as name of file_dir
        tmp = os.path.basename(file_dir)
        if tmp == '':
            file_dir = file_dir[:-1]
            tmp = os.path.basename(file_dir)

        self.data_name = tmp
        self.data_dir = file_dir

        # Make paths for analysis log file, dataset object savefile and hdf5
        self.log_file = os.path.join(file_dir, '%s_processing.log' % tmp)
        self.save_file = os.path.join(file_dir, '%s_dataset.p' % tmp)
        h5_file = dio.h5io.get_h5_filename(file_dir)
        if h5_file is None:
            h5_file = os.path.join(file_dir, '%s.h5' % tmp)

        self.h5_file = h5_file

        self.dataset_creation_date = dt.datetime.today()

        # Outline standard processing pipeline and status check
        self.processing_steps = ['extract_data', 'create_trial_list',
                                 'mark_dead_channels',
                                 'common_average_reference', 'blech_clust_run',
                                 'cleanup_clustering',
                                 'sort_units', 'make_unit_plots',
                                 'units_similarity', 'make_unit_arrays',
                                 'make_psth_arrays', 'plot_psths',
                                 'palatability_calculate', 'palatability_plot',
                                 'overlay_psth']
        self.process_status = dict.fromkeys(self.processing_steps, False)

    @Logger('Initializing Parameters')
    def initParams(self, data_quality='clean', emg_port=None,
                   emg_channels=None, car_keyword=None,
                   shell=False, dig_in_names=None,
                   dig_out_names=None, accept_params=False):
        '''
        Initalizes basic default analysis parameters and allows customization
        of parameters

        Parameters (all optional)
        -------------------------
        data_quality : {'clean', 'noisy'}
            keyword defining which default set of parameters to use to detect
            headstage disconnection during clustering
            default is 'clean'. Best practice is to run blech_clust as 'clean'
            and re-run as 'noisy' if too many early cutoffs occurr
        emg_port : str
            Port ('A', 'B', 'C') of EMG, if there was an EMG. None (default)
            will query user. False indicates no EMG port and not to query user
        emg_channels : list of int
            channel or channels of EMGs on port specified
            default is None
        car_keyword : str
            Specifes default common average reference groups
            defaults are found in CAR_defaults.json
            Currently 'bilateral32' is only keyword available
            If left as None (default) user will be queries to select common
            average reference groups
        shell : bool
            False (default) for GUI. True for command-line interface
        dig_in_names : list of str
            Names of digital inputs. Must match number of digital inputs used
            in recording.
            None (default) queries user to name each dig_in
        dig_out_names : list of str
            Names of digital outputs. Must match number of digital outputs in
            recording.
            None (default) queries user to name each dig_out
        accept_params : bool
            True automatically accepts default parameters where possible,
            decreasing user queries
            False (default) will query user to confirm or edit parameters for
            clustering, spike array and psth creation and palatability/identity
            calculations
        '''
        # Get parameters from info.rhd
        file_dir = self.data_dir
        rec_info = dio.rawIO.read_rec_info(file_dir)
        ports = rec_info.pop('ports')
        channels = rec_info.pop('channels')
        sampling_rate = rec_info['amplifier_sampling_rate']
        self.rec_info = rec_info
        self.sampling_rate = sampling_rate

        # Get default parameters from files
        clustering_params = dio.params.load_params('clustering_params', file_dir,
                                                   default_keyword=data_quality)
        spike_array_params = dio.params.load_params('spike_array_params', file_dir)
        psth_params = dio.params.load_params('psth_params', file_dir)
        pal_id_params = dio.params.load_params('pal_id_params', file_dir)
        spike_array_params['sampling_rate'] = sampling_rate
        clustering_params['file_dir'] = file_dir
        clustering_params['sampling_rate'] = sampling_rate

        # Setup digital input mapping
        #TODO: Setup digital output mapping...ignoring for now
        if rec_info.get('dig_in'):
            self._setup_din_mapping(rec_info, dig_in_names, shell)
            dim = self.dig_in_mapping.copy()
            spike_array_params['laser_channels'] = dim.channel[dim['laser']].to_list()
            spike_array_params['dig_ins_to_use'] = dim.channel[dim['spike_array']].to_list()

        # Setup electrode and emg mapping
        self._setup_channel_mappings(ports, channels, emg_port,
                                     emg_channels, shell=shell)

        # Set CAR groups
        self._set_CAR_groups(group_keyword=car_keyword, shell=shell)

        # Confirm parameters
        if not accept_params:
            conf = userIO.confirm_parameter_dict
            clustering_params = conf(clustering_params,
                                     'Clustering Parameters', shell=shell)
            self.spike_array_params = spike_array_params
            self.edit_spike_array_params(shell=shell)
            psth_params = conf(psth_params,
                               'PSTH Parameters', shell=shell)
            pal_id_params = conf(pal_id_params,
                                 'Palatability/Identity Parameters\n'
                                 'Valid unit_type is Single, Multi or All',
                                 shell=shell)

        # Store parameters
        self.clustering_params = clustering_params
        self.pal_id_params = pal_id_params
        self.psth_params = psth_params
        self._write_all_params_to_json()
        self.save()

    def _set_CAR_groups(self, group_keyword=None, shell=False):
        '''Sets that electrode groups for common average referencing and
        defines which brain region electrodes eneded up in

        Parameters
        ----------
        group_keyword : str or int
            Keyword corresponding to a preset electrode grouping in CAR_params.json
            Or integer indicating number of CAR groups
        shell : bool
            True for command-line interface, False (default) for GUI
        '''
        if not hasattr(self, 'electrode_mapping'):
            raise ValueError('Set electrode mapping before setting CAR groups')

        em = self.electrode_mapping.copy()

        car_param_file = os.path.join(self.data_dir, 'analysis_params',
                                      'CAR_params.json')
        if os.path.isfile(car_param_file):
            group_electrodes = dio.params.load_params('CAR_params',
                                                      self.data_dir)
        else:
            if group_keyword is None:
                group_keyword = userIO.get_user_input(
                    'Input keyword for CAR parameters or number of CAR groups',
                    shell=shell)

            if group_keyword is None:
                ValueError('Must provide a keyword or number of groups')
            elif group_keyword.isnumeric():
                num_groups = int(group_keyword)
                group_electrodes = dio.params.select_CAR_groups(num_groups, em,
                                                                shell=shell)
            else:
                group_electrodes = dio.params.load_params('CAR_params',
                                                          self.data_dir,
                                                          default_keyword=group_keyword)

        num_groups = len(group_electrodes)
        group_names = ['Group %i' % i for i in range(num_groups)]
        area_dict = dict.fromkeys(group_names, '')
        area_dict = userIO.fill_dict(area_dict, 'Set Areas for CAR groups',
                                     shell=shell)
        for k, v in area_dict.items():
            i = int(k.replace('Group', ''))
            em.loc[group_electrodes[i], 'area'] = v
            em.loc[group_electrodes[i], 'CAR_group'] = i

        self.CAR_electrodes = group_electrodes
        self.electrode_mapping = em.copy()

    def _setup_din_mapping(self, dig_in_names=None, shell=False):
        '''sets up dig_in_mapping dataframe  and queries user to fill in columns

        Parameters
        ----------
        dig_in_names : list of str (optional)
        shell : bool (optional)
            True for command-line interface
            False (default) for GUI
        '''
        rec_info = self.rec_info
        df = pd.DataFrame()
        df['channel'] = rec_info.get('dig_in')
        n_dig_in = len(df)
        # Names
        if dig_in_names:
            df['name'] = dig_in_names
        else:
            df['name'] = ''

        # Parameters to query
        df['palatability_rank'] = 0
        df['laser'] = False
        df['spike_array'] = True
        df['exclude'] = False
        # Re-format for query
        idx = df.index
        df.index = ['dig_in_%i' % x for x in df.channel]
        # Query for user input
        prompt = ('Digital Input Parameters\nSet palatability ranks from 1 to %i'
                  '\nor blank to exclude from pal_id analysis') % len(df)
        tmp = userIO.fill_dict(df.to_dict(), prompt=prompt, shell=shell)
        # Reformat for storage
        df2 = pd.DataFrame.from_dict(tmp)
        df2 = df2.sort_values(by=['channel'])
        df2.index = idx
        self.dig_in_mapping = df2.copy()

    def _setup_channel_mapping(self, ports, channels, emg_port, emg_channels, shell=False):
        '''Creates electrode_mapping and emg_mapping DataFrames with columns:
        - Electrode
        - Port
        - Channel

        Parameters
        ----------
        ports : list of str, item corresponing to each channel
        channels : list of int, channels on each port
        emg_port : str
        emg_channels : list of int
        '''
        if emg_port is None:
            q = userIO.ask_user('Do you have an EMG?', shell=shell)
            if q==0:
                emg_port = userIO.select_from_list('Select EMG Port:',
                                                   ports, 'EMG Port',
                                                   shell=shell)
                emg_channels = userIO.select_from_list(
                    'Select EMG Channels:',
                    [y for x, y in
                     zip(ports, channels)
                     if x == emg_port],
                    title='EMG Channels',
                    multi_select=True, shell=shell)

        el_map, em_map = dio.params.flatten_channels(ports, channels,
                                                     emg_port, emg_channels)
        self.electrode_mapping = el_map
        self.emg_mapping = em_map

    def edit_spike_array_params(self, shell=False):
        '''Edit spike array parameters and adjust dig_in_mapping accordingly

        Parameters
        ----------
        shell : bool, whether to use CLI or GUI
        '''
        if not hasattr(self, 'dig_in_mapping'):
            self.spike_array_params = None
            return

        sa = deepcopy(self.spike_array_params)
        tmp = userIO.fill_dict(sa, 'Spike Array Parameters\n(Times in ms)',
                               shell=shell)
        if tmp is None:
            return

        dim = self.dig_in_mapping
        dim['spike_array'] = False
        if tmp['dig_ins_to_use'] != ['']:
            tmp['dig_ins_to_use'] = [int(x) for x in tmp['dig_ins_to_use']]
            dim.loc[[x in tmp['dig_ins_to_use'] for x in dim.channel],
                    'spike_array'] = True

        dim['laser_channels'] = False
        if tmp['laser_channels'] != ['']:
            tmp['laser_channels'] = [int(x) for x in tmp['laser_channels']]
            dim.loc[[x in tmp['laser_channels'] for x in dim.channel],
                    'laser'] = True

        self.spike_array_params = tmp.copy()
        wt.write_params_to_json('spike_array_params',
                                self.data_dir, tmp)

    def edit_clustering_params(self, shell=False):
        '''Allows user interface for editing clustering parameters

        Parameters
        ----------
        shell : bool (optional)
            True if you want command-line interface, False for GUI (default)
        '''
        tmp = userIO.fill_dict(self.clustering_params,
                               'Clustering Parameters\n(Times in ms)',
                               shell=shell)
        if tmp:
            self.clustering_params = tmp
            wt.write_params_to_json('clustering_params', self.data_dir, tmp)

    def edit_psth_params(self, shell=False):
        '''Allows user interface for editing psth parameters

        Parameters
        ----------
        shell : bool (optional)
            True if you want command-line interface, False for GUI (default)
        '''
        tmp = userIO.fill_dict(self.psth_params,
                               'PSTH Parameters\n(Times in ms)',
                               shell=shell)
        if tmp:
            self.psth_params = tmp
            wt.write_params_to_json('psth_params', self.data_dir, tmp)

    def edit_pal_id_params(self, shell=False):
        '''Allows user interface for editing palatability/identity parameters

        Parameters
        ----------
        shell : bool (optional)
            True if you want command-line interface, False for GUI (default)
        '''
        tmp = userIO.fill_dict(self.pal_id_params,
                               'Palatability/Identity Parameters\n(Times in ms)',
                               shell=shell)
        if tmp:
            self.pal_id_params = tmp
            wt.write_params_to_json('pal_id_params', self.data_dir, tmp)

    def __str__(self):
        '''Put all information about dataset in string format

        Returns
        -------
        str : representation of dataset object
        '''
        out = [self.data_name]
        out.append('Data directory:  '+self.data_dir)
        out.append('Object creation date: '
                   + self.dataset_creation_date.strftime('%m/%d/%y'))
        out.append('Dataset Save File: ' + self.save_file)

        if hasattr(self, 'raw_h5_file'):
            out.append('Deleted Raw h5 file: '+self.raw_h5_file)
            out.append('h5 File: '+self.h5_file)
            out.append('')

        out.append('--------------------')
        out.append('Processing Status')
        out.append('--------------------')
        out.append(pt.print_dict(self.process_status))
        out.append('')

        if not hasattr(self, 'rec_info'):
            return '\n'.join(out)

        info = self.rec_info

        out.append('--------------------')
        out.append('Recording Info')
        out.append('--------------------')
        out.append(pt.print_dict(self.rec_info))
        out.append('')

        out.append('--------------------')
        out.append('Electrodes')
        out.append('--------------------')
        out.append(pt.print_dataframe(self.electrode_mapping))
        out.append('')

        if hasattr(self, 'CAR_electrodes'):
            out.append('--------------------')
            out.append('CAR Groups')
            out.append('--------------------')
            headers = ['Group %i' % x for x in range(len(self.CAR_electrodes))]
            out.append(pt.print_list_table(self.CAR_electrodes, headers))
            out.append('')

        if not self.emg_mapping.empty:
            out.append('--------------------')
            out.append('EMG')
            out.append('--------------------')
            out.append(pt.print_dataframe(self.emg_mapping))
            out.append('')

        if info.get('dig_in'):
            out.append('--------------------')
            out.append('Digital Input')
            out.append('--------------------')
            out.append(pt.print_dataframe(self.dig_in_mapping))
            out.append('')

        if info.get('dig_out'):
            out.append('--------------------')
            out.append('Digital Output')
            out.append('--------------------')
            out.append(pt.print_dataframe(self.dig_out_mapping))
            out.append('')

        out.append('--------------------')
        out.append('Clustering Parameters')
        out.append('--------------------')
        out.append(pt.print_dict(self.clust_params))
        out.append('')

        out.append('--------------------')
        out.append('Spike Array Parameters')
        out.append('--------------------')
        out.append(pt.print_dict(self.spike_array_params))
        out.append('')

        out.append('--------------------')
        out.append('PSTH Parameters')
        out.append('--------------------')
        out.append(pt.print_dict(self.psth_params))
        out.append('')

        out.append('--------------------')
        out.append('Palatability/Identity Parameters')
        out.append('--------------------')
        out.append(pt.print_dict(self.pal_id_params))
        out.append('')

        return '\n'.join(out)

    def _save_(self):
        '''Saves dataset object to dataset.p file in recording directory
        '''
        with open(self.save_file, 'wb') as f:
            pickle.dump(self, f)
            print('Saved dataset processing metadata to %s' % self.save_file)

    def _write_all_params_to_json(self):
        '''Writes all parameters to json files in analysis_params folder in the
        recording directory
        '''
        clustering_params = self.clustering_params
        spike_array_params = self.spike_array_params
        psth_params = self.psth_params
        pal_id_params = self.pal_id_params
        CAR_params = self.CAR_electrodes

        rec_dir = self.data_dir
        wt.write_params_to_json('clustering_params', rec_dir, clustering_params)
        wt.write_params_to_json('spike_array_params', rec_dir, spike_array_params)
        wt.write_params_to_json('psth_params', rec_dir, psth_params)
        wt.write_params_to_json('pal_id_params', rec_dir, pal_id_params)
        wt.write_params_to_json('CAR_params', rec_dir, CAR_params)

    @Logger('Extracting Data')
    def extract_data(self):
        '''Create hdf5 store for data and read in Intan .dat files. Also create
        subfolders for processing outputs

        Parameters
        ----------
        data_quality: {'clean', 'noisy'} (optional)
            Specifies quality of data for default clustering parameters
            associated. Should generally first process with clean (default)
            parameters and then try noisy after running blech_clust and
            checking if too many electrodes as cutoff too early
        '''
        if self.rec_info['file_type'] is None:
            raise ValueError('Unsupported recording type. Cannot extract yet.')

        if filename is None:
            filename = self.h5_file

        print('\nExtract Intan Data\n--------------------')
        # Create h5 file
        dio.h5io.create_empty_data_h5(filename, shell)

        # Create arrays for raw data in hdf5 store
        dio.h5io.create_hdf_arrays(filename, self.rec_info,
                                   self.electrode_mapping, self.emg_mapping)

        # Read in data to arrays
        dio.h5io.read_files_into_arrays(filename,
                                        self.rec_info,
                                        self.electrode_mapping,
                                        self.emg_mapping)

        # update status
        self.h5_file = filename
        self.process_status['extract_data'] = True
        self.save()
        print('\nData Extraction Complete\n--------------------')

    @Logger('Creating Trial List')
    def create_trial_list(self):
        '''Create lists of trials based on digital inputs and outputs and store
        to hdf5 store
        Can only be run after data extraction
        '''
        if not self.process_status['extract_data']:
            userIO.tell_user('Must extract data before creating trial list',shell=True)
            return

        if self.rec_info.get('dig_in'):
            in_list = dio.h5io.create_trial_data_table(
                self.h5_file,
                self.dig_in_mapping,
                self.sampling_rate,
                'in')
            self.dig_in_trials = in_list
        else:
            print('No digital input data found')

        if self.rec_info.get('dig_out'):
            out_list = dio.h5io.create_trial_data_table(
                self.h5_file,
                self.dig_out_mapping,
                self.sampling_rate,
                'out')
            self.dig_out_trials = out_list
        else:
            print('No digital output data found')

        self.process_status['create_trial_list'] = True
        self.save()

    @Logger('Marking Dead Channels')
    def mark_dead_channels(self, dead_channels=None, shell=False):
        '''Plots small piece of raw traces and a metric to help identify dead
        channels. Once user marks channels as dead a new column is added to
        electrode mapping

        Parameters
        ----------
        dead_channels : list of int, optional
            if this is specified then nothing is plotted, those channels are
            simply marked as dead
        shell : bool, optional
        '''
        em = self.electrode_mapping.copy()
        if dead_channels is None:
            userIO.tell_user('Making traces figure for dead channel detection...',
                             shell=True)
            save_file = os.path.join(self.data_dir, 'Electrode_Traces.png')
            fig, ax = datplt.plot_traces_and_outliers(self.h5_filei, save_file=save_file)
            if not shell:
                # Better to open figure outside of python since its a lot of
                # data on figure and matplotlib is slow
                subprocess.call(['xdg-open', save_file])
            else:
                userIO.tell_user('Saved figure of traces to %s for reference'
                                 % save_file, shell=shell)

            choice = userIO.select_from_list('Select dead channels:',
                                             em.Electrode.to_list(),
                                             'Dead Channel Selection',
                                             multi_select=True,
                                             shell=shell)
            dead_channels = list(map(int, choice))

        em['dead'] = False
        em.loc[dead_channels, 'dead'] = True
        self.electrode_mapping = em
        return dead_channels

    @Logger('Common Average Referencing')
    def common_average_reference(self):
        '''Define electrode groups and remove common average from  signals

        Parameters
        ----------
        num_groups : int (optional)
            number of CAR groups, if not provided
            there's a prompt
        '''
        if not hasattr(self, 'CAR_electrodes'):
            raise ValueError('CAR_electrodes not set')

        if not hasattr(self, 'electrode_mapping'):
            raise ValueError('electrode_mapping not set')

        car_electrodes = self.CAR_electrodes
        num_groups = len(car_electrodes)
        em = self.electrode_mapping.copy()

        if 'dead' in em.columns:
            dead_electrodes = em.Electrode[em.dead].to_list()
        else:
            dead_electrodes = []

        # Gather Common Average Reference Groups
        print('CAR Groups\n')
        headers = ['Group %i' % x for x in range(num_groups)]
        print(pt.print_list_table(car_electrodes, headers))

        # Reference each group
        for i, x in enumerate(car_electrodes):
            tmp = list(set(x) - set(dead_electrodes))
            dio.h5io.common_avg_reference(self.h5_file, tmp, i)

        # Compress and repack file
        dio.h5io.compress_and_repack(self.h5_file)

        self.process_status['common_average_reference'] = True
        self.save()

    @Logger('Running Blech Clust')
    def blech_clust_run(self, data_quality=None,
                        accept_params=False, shell=False):

        '''Write clustering parameters to file and
        Run blech_process on each electrode using GNU parallel

        Parameters
        ----------
        data_quality : {'clean', 'noisy', None (default)}
            set if you want to change the data quality parameters for cutoff
            and spike detection before running clustering. These parameters are
            automatically set as "clean" during initial parameter setup
        accept_params : bool, False (default)
            set to True in order to skip popup confirmation of parameters when
            running
        '''
        if data_quality:
            tmp = dio.params.load_params('clustering_params', self.data_dir,
                                         default_keyword=data_quality)
            if tmp:
                self.clustering_params = tmp
            else:
                raise ValueError('%s is not a valid data_quality preset. Must '
                                 'be "clean" or "noisy" or None.')

        print('\nRunning Blech Clust\n-------------------')
        print('Parameters\n%s' % pt.print_dict(self.clustering_params))

        # Write parameters into .params file
        self.param_file = os.path.join(self.data_dir, self.data_name+'.params')
        dio.params.write_clustering_params(self.param_file, self.clustering_params)

        # Create folders for saving things within recording dir
        data_dir = self.data_dir
        directories = ['spike_waveforms', 'spike_times',
                       'clustering_results',
                       'Plots', 'memory_monitor_clustering']
        for d in directories:
            tmp_dir = os.path.join(data_dir, d)
            if os.path.exists(tmp_dir):
                shutil.rmtree(tmp_dir)

            os.mkdir(tmp_dir)

        # Set file for clusting log
        self.clustering_log = os.path.join(data_dir, 'results.log')
        if os.path.exists(self.clustering_log):
            os.remove(self.clustering_log)

        process_path = os.path.realpath(__file__)
        process_path = os.path.join(os.path.dirname(process_path),
                                    'blech_process.py')
        em = self.electrode_mapping
        if 'dead' in em.columns:
            electrodes = em.Electrode[em['dead'] == False].tolist()
        else:
            electrodes = em.Electrode.tolist()

        my_env = os.environ
        my_env['OMP_NUM_THREADS'] = '1'  # possibly not necesary
        cpu_count = int(multiprocessing.cpu_count())-1
        process_call = ['parallel', '-k', '-j', str(cpu_count), '--noswap',
                        '--load', '100%', '--progress', '--memfree', '4G',
                        '--retry-failed', '--joblog', self.clustering_log,
                        'python', process_path, '{1}', self.data_dir, ':::']
        process_call.extend([str(x) for x in electrodes])
        subprocess.call(process_call, env=my_env)
        self.process_status['blech_clust_run'] = True
        self.save()
        print('Clustering Complete\n------------------')

    @Logger('Cleaning up clustering memory logs. Removing raw data and setting'
            'up hdf5 for unit sorting')
    def cleanup_clustering(self):
        '''Consolidates memory monitor files, removes raw and referenced data
        and setups up hdf5 store for sorted units data
        '''
        h5_file = dio.h5io.cleanup_clustering(self.data_dir)
        self.h5_file = h5_file
        self.process_status['cleanup_clustering'] = True
        self.save()

    def sort_units(self):
        '''Begins processes to allow labelling of clusters as sorted units

        Parameters
        ----------
        shell : bool
            True if command-line interfaced desired, False for GUI (default)
        '''
        fs = self.sampling_rate
        ss.sort_units(self.data_dir, fs, shell)
        self.process_status['sort_units'] = True
        self.save()

    @Logger('Making Unit Arrays')
    def make_unit_arrays(self):
        '''Make spike arrays for each unit and store in hdf5 store
        '''
        params = self.spike_array_params

        print('Generating unit arrays with parameters:\n----------')
        print(pt.print_dict(params, tabs=1))
        ss.make_spike_arrays(self.h5_file, params)
        self.process_status['make_unit_arrays'] = True
        self.save()

    @Logger('Making Unit Plots')
    def make_unit_plots(self):
        '''Make waveform plots for each sorted unit
        '''
        ss.make_unit_plots(self.data_dir, self.sampling_rate)
        self.process_status['make_unit_plots'] = True
        self.save()

    @Logger('Making PSTH Arrays')
    def make_psth_arrays(self):
        '''Make smoothed firing rate traces for each unit/trial and store in
        hdf5 store
        '''
        params = self.psth_params
        dig_ins = self.dig_in_mapping
        for idx, row in dig_ins.iterrows():
            spike_analysis.make_psths_for_tastant(self.h5_file,
                                                  params['window_size'],
                                                  params['window_step'],
                                                  row['channel'])

        self.process_status['make_psth_arrays'] = True
        self.save()

    @Logger('Calculating Palatability/Identity Metrics')
    def palatability_calculate(self, shell=False):
        pal_analysis.palatability_identity_calculations(self.data_dir,
                                                        params=self.pal_id_params)
        self.process_status['palatability_calculate'] = True
        self.save()

    @Logger('Plotting Palatability/Identity Metrics')
    def palatability_plot(self, shell=False):
        pal_plt.plot_palatability_identity([self.data_dir], shell=shell)
        self.process_status['palatability_plot'] = True
        self.save()

    def get_unit_table(self):
        '''Returns a pandas dataframe with sorted unit information

        Returns
        --------
        pandas.DataFrame with columns:
            unit_name, unit_num, electrode, single_unit,
            regular_spiking, fast_spiking
        '''
        unit_table = dio.h5io.get_unit_table(self.data_dir)
        return unit_table

    def extract_and_cluster(self, shell=False):
        pass

    def post_sorting(self):
        pass
