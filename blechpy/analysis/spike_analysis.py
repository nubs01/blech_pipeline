import numpy as np


def make_single_trial_psth(spike_train, win_size, win_step, time=None):
    '''Takes a spike train and returns firing rate trace in Hz

    Parameters
    ----------
    spike_train : 1D numpy.array
        spike train with 1s in bins with spikes and 0s elsewhere
    win_size : float, window size of psth in ms
    win_step : float, step size of psth in ms
    time : numpy.array (optional)
        time array with times corresponding to bins in spike_train
        if not provided then on is created starting at 0 and assuming 1ms bins

    Returns
    -------
    psth : numpy.array, firing rate vector with units of Hz
    psth_time: numpy.array, time vector corresponding to the psth
    '''
    if time is None:
        time = np.arange(0, len(spike_train), 1)  # assume 1ms bins

    psth_time = np.arange(np.min(time) + (win_size/2),
                          np.max(time) - (win_size/2),
                          win_step)
    psth = np.zeros(psth_time.shape)
    window = np.array([-win_size/2, win_size/2])

    for i, t in enumerate(psth_time):
        t_win = t + window
        idx = np.where((time >= t_win[0]) & (time <= t_win[1]))[0]
        psth[i] = np.sum(spike_train[idx]) / (win_size/1000.0)  # in Hz

    return psth, psth_time

def make_PSTH_array(h5_file, win_size, win_step, dig_in_ch):

    with tables.open_file(h5_file, 'r') as hf5:
        spike_data = hf5.root.spike_trains['dig_in_%i' % dig_in_ch]
        spike_array = spike_data.spike_array[:]
        time = spike_data.array_time

        psth_time = np.arange(np.min(time) - (win_size/2),
                              np.max(time) + (win_size/2),
                              win_step)
        PSTHs = np.zeros((len(psth_time), spike_array.shape[1]))

        for trial in spike_array:
            for i, unit in enumerate(trial):
                tmp, tmp_time = make_single_trial_psth(unit, win_size,
                                                       win_step, time)
                PSTHs[:, i] += tmp
        PSTHs /= spike_array.shape[0]

    return PSTHs




