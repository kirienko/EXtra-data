import os.path as osp
from tempfile import TemporaryDirectory

import h5py
import numpy as np
import pytest
from testpath import assert_isfile

from extra_data import H5File
from extra_data.components import AGIPD1M
from extra_data.exceptions import TrainIDError
from extra_data.file_access import FileAccess
from . import make_examples

@pytest.fixture(scope='module')
def agipd_file_tid_very_high():
    with TemporaryDirectory() as td:
        path = osp.join(td, 'CORR-R9999-AGIPD07-S00000.h5')
        make_examples.make_agipd_example_file(path, format_version='0.5')
        with h5py.File(path, 'r+') as f:
            # Initial train IDs are np.arange(10000, 10250)
            f['INDEX/trainId'][10] = 11000
        yield path

@pytest.fixture(scope='module')
def agipd_file_tid_high():
    with TemporaryDirectory() as td:
        path = osp.join(td, 'CORR-R9999-AGIPD07-S00000.h5')
        make_examples.make_agipd_file(path, format_version='0.5')
        with h5py.File(path, 'r+') as f:
            # Initial train IDs are np.arange(10000, 10250), this will appear 2x
            f['INDEX/trainId'][10] = 10100
        yield path

@pytest.fixture(scope='module')
def agipd_file_tid_low():
    with TemporaryDirectory() as td:
        path = osp.join(td, 'CORR-R9999-AGIPD07-S00000.h5')
        make_examples.make_agipd_example_file(path, format_version='0.5')
        with h5py.File(path, 'r+') as f:
            # Initial train IDs are np.arange(10000, 10250)
            f['INDEX/trainId'][20] = 9000
        yield path

@pytest.fixture()
def agipd_file_flag0():
    with TemporaryDirectory() as td:
        path = osp.join(td, 'CORR-R9999-AGIPD07-S00000.h5')
        make_examples.make_agipd_file(path, format_version='1.0')
        with h5py.File(path, 'r+') as f:
            f['INDEX/flag'][30] = 0
        yield path

def test_guess_validity(agipd_file_tid_very_high, agipd_file_tid_high, agipd_file_tid_low):
    fa = FileAccess(agipd_file_tid_very_high)
    assert fa.validity_flag.sum() == 249
    assert not fa.validity_flag[10]

    fa = FileAccess(agipd_file_tid_high)
    assert fa.validity_flag.sum() == 485
    assert not fa.validity_flag[10]

    fa = FileAccess(agipd_file_tid_low)
    assert fa.validity_flag.sum() == 249
    assert not fa.validity_flag[20]

def test_validity_flag(agipd_file_flag0):
    fa = FileAccess(agipd_file_flag0)
    assert fa.validity_flag.sum() == 485
    assert not fa.validity_flag[30]

def test_exc_trainid(agipd_file_tid_very_high, agipd_file_tid_high, agipd_file_tid_low, agipd_file_flag0):
    f = H5File(agipd_file_tid_very_high)
    assert len(f.train_ids) == 249
    assert 11000 not in f.train_ids

    f = H5File(agipd_file_tid_very_high, inc_suspect_trains=True)
    assert len(f.train_ids) == 250
    assert 11000 in f.train_ids

    f = H5File(agipd_file_tid_high)
    assert len(f.train_ids) == 485
    assert 10100 in f.train_ids

    f = H5File(agipd_file_tid_high, inc_suspect_trains=True)
    assert len(f.train_ids) == 485  # this list is always deduped & sorted
    assert 10100 in f.train_ids

    f = H5File(agipd_file_tid_low)
    assert len(f.train_ids) == 249
    assert 9000 not in f.train_ids

    f = H5File(agipd_file_tid_low, inc_suspect_trains=True)
    assert len(f.train_ids) == 250
    assert 9000 in f.train_ids

    f = H5File(agipd_file_flag0)
    assert len(f.train_ids) == 485
    assert 10030 not in f.train_ids

    f = H5File(agipd_file_flag0, inc_suspect_trains=True)
    assert len(f.train_ids) == 486
    assert 10030 in f.train_ids

# If the tests above pass, the invalid trains in the different sample files
# are being recognised correctly. So for the tests below, we'll mainly test
# each behaviour on just one of the sample files.

def test_keydata_interface(agipd_file_tid_very_high):
    f = H5File(agipd_file_tid_very_high)
    kd = f['SPB_DET_AGIPD1M-1/DET/7CH0:xtdf', 'image.data']
    assert len(kd.train_ids) == 249
    assert kd.shape == (249 * 64, 512, 128)

    f = H5File(agipd_file_tid_very_high, inc_suspect_trains=True)
    kd = f['SPB_DET_AGIPD1M-1/DET/7CH0:xtdf', 'image.data']
    assert len(kd.train_ids) == 250
    assert kd.shape == (250 * 64, 512, 128)

def test_array(agipd_file_tid_low):
    f = H5File(agipd_file_tid_low)
    arr = f['SPB_DET_AGIPD1M-1/DET/7CH0:xtdf', 'image.pulseId'].xarray()
    assert arr.shape == (249 * 64, 1)

    f = H5File(agipd_file_tid_low, inc_suspect_trains=True)
    arr = f['SPB_DET_AGIPD1M-1/DET/7CH0:xtdf', 'image.pulseId'].xarray()
    assert arr.shape == (250 * 64, 1)

def test_array_dup(agipd_file_tid_high):
    f = H5File(agipd_file_tid_high)
    arr = f['SPB_DET_AGIPD1M-1/DET/0CH0:xtdf', 'image.pulseId'].xarray()
    assert arr.shape == (485 * 64, 1)
    assert list(arr.coords['trainId'].values[(9*64):(11*64):64]) == [10009, 10011]

    f = H5File(agipd_file_tid_high, inc_suspect_trains=True)
    arr = f['SPB_DET_AGIPD1M-1/DET/0CH0:xtdf', 'image.pulseId'].xarray()
    assert arr.shape == (486 * 64, 1)
    assert list(arr.coords['trainId'].values[(9 * 64):(11 * 64):64]) == [10009, 10100]

def test_dask_array(agipd_file_flag0):
    f = H5File(agipd_file_flag0)
    arr = f['SPB_DET_AGIPD1M-1/DET/0CH0:xtdf', 'image.pulseId'].dask_array()
    assert arr.shape == (485 * 64, 1)

    f = H5File(agipd_file_flag0, inc_suspect_trains=True)
    arr = f['SPB_DET_AGIPD1M-1/DET/0CH0:xtdf', 'image.pulseId'].dask_array()
    assert arr.shape == (486 * 64, 1)

def test_iterate_keydata(agipd_file_tid_very_high):
    f = H5File(agipd_file_tid_very_high)
    kd = f['SPB_DET_AGIPD1M-1/DET/7CH0:xtdf', 'image.pulseId']
    tids = [t for (t, _) in kd.trains()]
    assert len(tids) == 249
    assert 11000 not in tids

    f = H5File(agipd_file_tid_very_high, inc_suspect_trains=True)
    kd = f['SPB_DET_AGIPD1M-1/DET/7CH0:xtdf', 'image.pulseId']
    tids = [t for (t, _) in kd.trains()]
    assert len(tids) == 250
    assert 11000 in tids

def test_iterate_keydata_dup(agipd_file_tid_high):
    f = H5File(agipd_file_tid_high)
    kd = f['SPB_DET_AGIPD1M-1/DET/0CH0:xtdf', 'image.pulseId']
    tids = [t for (t, _) in kd.trains()]
    assert len(tids) == 485
    assert 10100 in tids
    assert tids[9:11] == [10009, 10011]

def test_get_train_keydata(agipd_file_tid_low):
    f = H5File(agipd_file_tid_low)
    kd = f['SPB_DET_AGIPD1M-1/DET/7CH0:xtdf', 'image.pulseId']
    with pytest.raises(TrainIDError):
        kd.train_from_id(9000)

    f = H5File(agipd_file_tid_low, inc_suspect_trains=True)
    kd = f['SPB_DET_AGIPD1M-1/DET/7CH0:xtdf', 'image.pulseId']
    assert kd.train_from_id(9000)[0] == 9000

def test_components_array(agipd_file_flag0):
    f = H5File(agipd_file_flag0)
    agipd = AGIPD1M(f, modules=[0])
    arr = agipd.get_array('image.data', pulses=np.s_[:1])
    assert arr.shape == (1, 485, 1, 2, 512, 128)
    assert arr.dims == ('module', 'train', 'pulse', 'data_gain', 'slow_scan', 'fast_scan')

def test_components_array_dup(agipd_file_tid_high):
    f = H5File(agipd_file_tid_high)
    agipd = AGIPD1M(f, modules=[0])
    arr = agipd.get_array('image.data', pulses=np.s_[:1])
    assert arr.shape == (1, 485, 1, 2, 512, 128)
    assert arr.dims == ('module', 'train', 'pulse', 'data_gain', 'slow_scan', 'fast_scan')
    assert list(arr.coords['train'].values[9:11]) == [10009, 10011]

def test_write_virtual_cxi_dup(agipd_file_tid_high, tmp_path, caplog):
    f = H5File(agipd_file_tid_high)
    agipd = AGIPD1M(f, modules=[0])
    cxi_path = tmp_path / 'exc_suspect.cxi'
    agipd.write_virtual_cxi(str(cxi_path))
    assert_isfile(cxi_path)
    with h5py.File(cxi_path, 'r') as f:
        assert f['entry_1/data_1/data'].shape == (485 * 64, 16, 2, 512, 128)

    f = H5File(agipd_file_tid_high, inc_suspect_trains=True)
    agipd = AGIPD1M(f, modules=[0])
    with pytest.raises(AssertionError):
        agipd.write_virtual_cxi(str(tmp_path / 'inc_suspect.cxi'))
