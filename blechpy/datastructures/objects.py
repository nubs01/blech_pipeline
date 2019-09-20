import os
from blechpy.utils import userIO

class data_object(object):
    def __init__(self, data_type, root_dir=None, data_name=None, savefile=None, logfile=None):
        if 'SSH_CONNECTION' in os.environ:
            shell = True
        else:
            shell = False

        if root_dir is None:
            root_dir = userIO.get_filedirs('Select %s directory' % data_type,
                                           shell=shell)
            if root_dir is None or not os.path.isdir(root_dir):
                raise NotADirectoryError('Must provide a valid root directory for the %s' % data_type)

        if root_dir.endswith('/'):
            root_dir = root_dir[:-1]

        if data_name is None:
            data_name = userIO.get_user_input('Enter name for %s' % data_type,
                                              os.path.basename(root_dir), shell)

        if savefile is None:
            savefile = os.path.join(root_dir, '%s_%s.p'
                                    % (os.path.basename(root_dir), data_type))

        if logfile is None:
            logfile = os.path.join(root_dir, '%s_%s.log'
                                   % (os.path.basename(root_dir), data_type))

        self.root_dir = root_dir
        self.data_type = data_type
        self.data_name = data_name
        self.save_file = savefile
        self.log_file = logfile

    def save(self):
        with open(self.save_file, 'wb') as f:
            pickle.dump(self, f)
            print('Saved %s to %s' % (self.name, self.save_file))

    def _change_root(self, new_root=None):
        if 'SSH_CONNECTION' in os.environ:
            shell = True
        else:
            shell = False

        if new_root is None:
            new_root = userIO.get_filedirs('Select new location of %s' % self.root_dir, shell=shell)

        old_root = self.root_dir
        self.root_dir = self.root_dir.replace(old_root, new_root)
        self.save_file = self.save_file.replace(old_root, new_root)
        self.log_file = self.log_file.replace(old_root, new_root)
        return new_root

    def __str__(self):
        out = []
        out.append(self.data_type + ' :: ' + self.data_name)
        out.append('Root Directory : %s' % self.root_dir)
        out.append('Save File : %s' % self.save_file)
        out.append('Log File : %s' % self.log_file)
        return '\n'.join(out)


def load_data(data_type, file_dir=None):
    '''Loads a data_object .p file and returns the object

    Parameters
    ----------
    data_type : str
        type of data_object extension do you want
        dataset, experiment or object
    file_dir : str (optional)
        path to file dir that the .p file is saved in

    Returns
    -------
    blechpy.data_object

    Raises
    ------
    NotADirectoryError
    '''
    if 'SSH_CONNECTION' in os.environ:
        shell = True
    else:
        shell = False

    if file_dir is None:
        file_dir = userIO.get_filedirs('Select %s directory' % data_type,
                                       shell=shell)

    if not os.path.isdir(file_dir):
        raise NotADirectoryError('%s not found.' % file_dir)

    data_file = [x for x in os.listdir(file_dir) if x.endswith('%s.p' % data_type)]

    if len(data_file) == 0:
        return None
    elif len(data_file) > 1:
        tmp = userIO.select_from_list('Multiple %s files found.'
                                      'Select the one you want to load.'
                                      % data_type, data_file, shell=shell)
        if tmp is None:
            return None
        else:
            data_file = tmp

    data_file = os.path.join(file_dir, data_file)
    with open(data_file, 'wb') as f:
        out = pickle.load(f)

    return out

def load_experiment(file_dir=None):
    '''Loads experiment.p file from file_dir

    Parameters
    ----------
    file_dir : str (optional), if not provided, file chooser will appear

    Returns
    -------
    blechpy.experiment or None if no file found
    '''
    return load_data('experiment', file_dir)

def load_dataset(file_dir=None):
    '''Loads dataset.p file from file_dir

    Parameters
    ----------
    file_dir : str (optional), if not provided, file chooser will appear

    Returns
    -------
    blechpy.dataset or None if no file found
    '''
    return load_data('dataset', file_dir)

def load_project(file_dir=None):
    '''Loads project.p file from file_dir

    Parameters
    ----------
    file_dir : str (optional), if not provided, file chooser will appear

    Returns
    -------
    blechpy.proejct or None if no file found
    '''
    return load_data('project', file_dir)



