import os, time
import easygui as eg
import numpy as np
import pandas as pd
from blechpy.dio import rawIO
from blechpy.data_print import data_print as dp

clustering_params = {'Max Number of Clusters':7,
                    'Max Number of Iterations':1000,
                    'Convergence Criterion':0.001,
                    'GMM random restarts':10}

data_params = {'clean':{'V_cutoff for disconnected headstage':1500,
                        'Max rate of cutoff breach per second':0.2,
                        'Max allowed seconds with a breach': 10,
                        'Max allowed breacher per second':20,
                        'Intra-cluster waveform amp SD cutoff':3},
                'noisy':{'V_cutoff for disconnected headstage':3000,
                        'Max rate of cutoff breach per second':2,
                        'Max allowed seconds with a breach': 20,
                        'Max allowed breacher per second':40,
                        'Intra-cluster waveform amp SD cutoff':3}}

bandpass_params = {'Lower freq cutoff':300,
                    'Upper freq cutoff':3000} # in Hz

spike_snapshot = {'Time before spike (ms)':.5,
                    'Time after spike (ms)':1} # in ms

clust_param_order = ['Max Number of Clusters','Max Number of Iterations',
                    'Convergence Criterion','GMM random restarts']
data_param_order = ['V_cutoff for disconnected headstage',
                    'Max rate of cutoff breach per second',
                    'Max allowed seconds with a breach',
                    'Intra-cluster waveform amp SD cutoff']
band_param_order = ['Lower freq cutoff','Upper freq cutoff']
spike_snap_order = ['Time before spike (ms)','Time after spike (ms)']

def Timer(heading):
    def real_timer(func):
        def wrapper(*args,**kwargs):
            start = time.time()
            print('')
            print('----------\n%s\n----------' % heading)
            result = func(*args,**kwargs)
            print('Done! Elapsed Time: %1.2f' % (time.time()-start))
            return result
        return wrapper
    return real_timer

def parse_amplifier_files(file_dir):
    '''
    parses the filenames of amp-*-*.dat files in file_dir and returns port and
    channel numbers
    for 'one file per channel' recordings

    deprecated: get ports and channels from rawIO.read_recording_info instead
    '''
    file_list = os.listdir(file_dir)
    ports = []
    channels = []
    for f in file_list:
        if f.startswith('amp'):
            tmp = f.replace('.dat','').split('-')
            if tmp[1] in ports:
                idx = ports.index(tmp[1])
                channels[idx].append(int(tmp[2]))
            else:
                ports.append(tmp[1])
                channels.append([int(tmp[2])])
    for c in channels:
        c.sort()
    return ports,channels

def parse_board_files(file_dir):
    '''
    parses board-*-*.dat files and returns lists of DIN and DOUT channels
    for 'one file per channel' type recordings

    deprecated: get DIN and DOUT from rawIO.read_recording_info instead
    '''
    file_list = os.listdir(file_dir)
    DIN = []
    DOUT = []
    for f in file_list:
        if f.startswith('board'):
            tmp = f.replace('.dat','').split('-')
            if tmp[1] == 'DIN':
                DIN.append(int(tmp[2]))
            elif tmp[1] == 'DOUT':
                DOUT.append(int(tmp[2]))
    return DIN,DOUT


def get_ports(file_dir):
    '''
    reads the data files in file_dir and returns a list of amplifier ports

    deprecated: get ports and channels from rawIO.read_recording_info instead
    '''
    ports,ch = parse_amplifier_files(file_dir)
    return ports

def get_channels_on_port(file_dir,port):
    '''
    reads files in file_dir to determine which amplifier channels are on port

    deprecated: get ports and channels from rawIO.read_recording_info instead
    '''
    ports,ch = parse_amplifier_files(file_dir)
    try:
        idx = ports.index(port)
    except ValueErrori as error:
        raise ValueError('Files for port %s not found in %s' % (port,file_dir)) from error
    return ch[idx]

def get_sampling_rate(file_dir):
    '''
    uses info.rhd in file_dir to get sampling rate of the data

    deprecated: get ports and channels from rawIO.read_recording_info instead
    '''
    sampling_rate = np.fromfile(os.path.join(file_dir,'info.rhd'), dtype = np.dtype('float32'))
    sampling_rate = int(sampling_rate[2])
    return sampling_rate

def get_din_channels(file_dir):
    '''
    returns a list of DIN channels read from filenames in file_dir

    deprecated: get ports and channels from rawIO.read_recording_info instead
    '''
    DIN,DOUT = parse_board_files(file_dir)
    return DIN

@Timer('Collecting parameters for common average referencing')
def get_CAR_params(file_dir,electrode_mapping,num_groups):
    '''
    BROKEN: Use electrode number instead of ports and channels
    Returns a dict containing standard params for common average referencing
    Each dict field with fields, num groups, ports, channels, emg port and emg
    channels
    Can set num_groups to an integer or as unilateral or bilateral
    Settings as unilateral or bilateral will automatically assign channels to
    groups, setting to a number will allow choice of channels for each group
    unilateral: 1 CAR group, all channels on port
    bilateral: 2 CAR groups, [0-7,24-31] & [8-23], assumes same port for both
    '''
    if num_groups=='bilateral':
        num_groups = 2
        implant_type = 'bilateral'
    elif num_groups=='unilateral':
        num_groups = 1
        implant_type = 'unilateral'
    elif isinstance(num_groups,int) and num_groups>0:
        implant_type=None
    else:
        raise ValueError('Num groups must be an integer >0 or a string bilateral or unlateral')

    electrodes = electrode_mapping['Electrode'].tolist()
    car_electrodes = []
    if implant_type=='bilateral':
        g1 = electrodes[:8]
        g2 = elecctrodes[-8:]
        car_electrodes = [g1,g2]
    elif implant_type=='unilateral':
        car_electrodes.append(electrodes)
    else:
        select_list = []
        for idx,row in electrode_mapping.iterrows():
            select_list.append(', '.join([str(x) for x in row]))
        for i in range(num_groups):
            tmp = select_from_list('Choose CAR electrodes for group %i: [Electrode, Port, Channel]' % i,
                                    'Group %i Electrodes' % i,select_list,multi_select=True)
            if tmp is None:
                raise ValueError('Must select electrodes for CAR groups')
            car_electrodes.append([int(x.split(',')[0]) for x in tmp])

    out = {'num groups':num_groups,'car_electrodes':car_electrodes}
    return out

@Timer('Writing Clustering Parameters to .params File')
def write_params(file_name,params):
    '''
    Writes parameters into a file for use by blech_process.py
    '''
    if not file_name.endswith('.params'):
        file_name += '.params'
    print('File: ' + file_name)
    dp.print_dict(params)
    with open(file_name,'w') as f:
        for c in clust_param_order:
            print(params['clustering_params'][c],file=f)
        for c in data_param_order:
            print(params['data_params'][c],file=f)
        for c in band_param_order:
            print(params['bandpass_params'][c],file=f)
        for c in spike_snap_order:
            print(params['spike_snapshot'][c],file=f)


def select_from_list(prompt,title,items,multi_select=False):
    '''
    makes a popup for list selections, can be multichoice or single choice
    default is single selection
    '''
    if multi_select is False:
        choice = eg.choicebox(prompt,title,items)
    else:
        choice = eg.multchoicebox(prompt,title,items,None)

    return choice

def flatten_channels(ports,channels,emg_port=None,emg_channels=None):
    '''takes all ports and all channels and makes a dataframe mapping ports and
    channels to electrode numbers from 0 to N
    excludes emg_channels if given

    Parameters
    ----------
    ports : list, list of port names, length equal to channels
    channels : list, list of channels number, corresponding to elements of ports
    emg_port : str (optional), prefix of port with EMG channel. Default is None
    emg_channels: list (optional), list of channels on emg_port used for emg

    Returns
    -------
    electrode_mapping : pandas.DataFrame, 
                        3 columns: Electrode, Port and Channel
    emg_mapping : pandas.DataFrame,
                    3 columns: EMG, Port, and Channel

    Throws
    ------
    ValueError : if length of ports is not equal to length of channels
    '''
    el_map = []
    em_map = []
    ports = ports.copy()
    channels = channels.copy()
    to_pop = []
    for idx,p in enumerate(zip(ports,channels)):
        if p[0]==emg_port and p[1] in emg_channels:
            em_map.append(p)
        else:
            el_map.append(p)

    map_df = pd.DataFrame(el_map,columns=['Port','Channel'])
    map_df.sort_values(by=['Port','Channel'],ascending=True,inplace=True)
    map_df.reset_index(drop=True,inplace=True)
    map_df = map_df.reset_index(drop=False).rename(columns={'index':'Electrode'})

    emg_df = pd.DataFrame(em_map,columns=['Port','Channel'])
    emg_df.sort_values(by=['Port','Channel'],ascending=True,inplace=True)
    emg_df.reset_index(drop=True,inplace=True)
    emg_df = emg_df.reset_index(drop=False).rename(columns={'index':'EMG'})
    return map_df, emg_df
