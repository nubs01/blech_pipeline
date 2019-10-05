import tables

class trial_info_particle(tables.IsDescription):
    '''PyTables particle for recording digital input (taste) trial info/order
    '''
    trial_num = tables.UInt16Col()
    channel = tables.Int16Col()
    name = tables.StringCol(20)
    on_index = tables.Int32Col()
    off_index = tables.Int32Col()
    on_time = tables.Float32Col()
    off_time = tables.Float32Col()


class unit_descriptor(tables.IsDescription):
    '''PyTables particles for storing sorted unit information 
    '''
    electrode_number = tables.Int32Col()
    single_unit = tables.Int32Col()
    regular_spiking = tables.Int32Col()
    fast_spiking = tables.Int32Col()


class electrode_map_particle(tables.IsDescription):
    '''PyTables particle for storing electrode mapping
    '''
    Electrode = tables.Int16Col()
    Port = tables.StringCol(5)
    Channel = tables.Int16Col()
    area = tables.StringCol(20)
    CAR_group = tables.Int16Col()
    dead = tables.BoolCol()
    cutoff_time = tables.Float32Col()
    clustering_result = tables.Int16Col()


class digital_mapping_particle(tables.IsDescription):
    '''Pytables particle for storing digital input/output mappings
    '''
    channel = tables.Int16Col()
    name = tables.StringCol(20)
    palatability_rank = tables.Int16Col()
    laser = tables.BoolCol()
    spike_array = tables.BoolCol()
    exclude = tables.BoolCol()
    laser_channels = tables.BoolCol()