import numpy as np

class KeyData:
    def __init__(self, source, key, data_chunks, section):
        self.source = source
        self.key = key
        self.section = section

        dim0 = 0
        entry_shapes, dtypes = set(), set()
        for chunk in data_chunks:
            dim0 += chunk.total_count
            entry_shapes.add(chunk.dataset.shape[1:])
            dtypes.add(chunk.dataset.dtype)

        if len(entry_shapes) > 1:
            raise Exception("Mismatched data shapes: {}".format(entry_shapes))
        if len(dtypes) > 1:
            raise Exception("Mismatched dtypes: {}".format(dtypes))

        self.dtype = dtypes.pop()
        self.entry_shape = entry_shapes.pop()
        self.shape = (dim0,) + self.entry_shape
        self.ndim = len(self.shape)
        # Sort chunks by train ID and discard any empty ones
        self._data_chunks = sorted(
            [c for c in data_chunks if c.total_count > 0],
            key=lambda c: c.train_ids[0]
        )
        if self._data_chunks:
            self.train_ids = np.concatenate([c.train_ids for c in self._data_chunks])
        else:
            self.train_ids = np.zeros(shape=(0,), dtype=np.uint64)

    def __repr__(self):
        return f"<extra_data.KeyData source={self.source!r} key={self.key!r} " \
               f"for {len(self.train_ids)} trains"

    @property
    def _key_group(self):
        """The part of the key needed to look up index data"""
        if self.section == 'INSTRUMENT':
            return self.key.partition('.')[0]
        else:
            return ''

    @property
    def _data_path(self):
        return f"/{self.section}/{self.source}/{self.key.replace('.', '/')}"

    def ndarray(self, roi=()):
        if not isinstance(roi, tuple):
            roi = (roi,)

        # Find the shape of the array with the ROI applied
        roi_dummy = np.zeros((0,) + self.entry_shape) # extra 0 dim: use less memory
        roi_shape = roi_dummy[np.index_exp[:] + roi].shape[1:]

        out = np.empty(self.shape[:1] + roi_shape, dtype=self.dtype)

        # Read the data from each chunk into the result array
        dest_cursor = 0
        for chunk in self._data_chunks:
            dest_chunk_end = dest_cursor + chunk.total_count

            slices = (chunk.slice,) + roi
            chunk.dataset.read_direct(
                out[dest_cursor:dest_chunk_end], source_sel=slices
            )
            dest_cursor = dest_chunk_end

        return out

    def _trainid_index(self):
        """A 1D array of train IDs, corresponding to self.shape[0]"""
        chunks_trainids = [
            np.repeat(chunk.train_ids, chunk.counts.astype(np.intp))
            for chunk in self._data_chunks
        ]
        return np.concatenate(chunks_trainids)

    def xarray(self, extra_dims=None, roi=()):
        import xarray

        ndarr = self.ndarray(roi=roi)

        # Dimension labels
        if extra_dims is None:
            extra_dims = ['dim_%d' % i for i in range(ndarr.ndim - 1)]
        dims = ['trainId'] + extra_dims

        # Train ID index
        coords = {}
        if self.shape[0]:
            coords = {'trainId': self._trainid_index()}

        return xarray.DataArray(ndarr, dims=dims, coords=coords)

    def series(self):
        import pandas as pd

        if self.ndim > 1:
            raise TypeError("pandas Series are only available for 1D data")

        name = self.source + '/' + self.key
        if name.endswith('.value'):
            name = name[:-6]

        index = pd.Index(self._trainid_index(), name='trainId')
        data = self.ndarray()
        return pd.Series(data, name=name, index=index)

    def dask_array(self, labelled=False):
        import dask.array as da

        chunks_darrs = []

        for chunk in self._data_chunks:
            chunk_dim0 = chunk.total_count
            chunk_shape = (chunk_dim0,) + chunk.dataset.shape[1:]
            itemsize = chunk.dataset.dtype.itemsize

            # Find chunk size of maximum 2 GB. This is largely arbitrary:
            # we want chunks small enough that each worker can have at least
            # a couple in memory (Maxwell nodes have 256-768 GB in late 2019).
            # But bigger chunks means less overhead.
            # Empirically, making chunks 4 times bigger/smaller didn't seem to
            # affect speed dramatically - but this could depend on many factors.
            # TODO: optional user control of chunking
            limit = 2 * 1024 ** 3
            while np.product(chunk_shape) * itemsize > limit and chunk_dim0 > 1:
                chunk_dim0 //= 2
                chunk_shape = (chunk_dim0,) + chunk.dataset.shape[1:]

            chunks_darrs.append(
                da.from_array(
                    chunk.file.dset_proxy(chunk.dataset_path), chunks=chunk_shape
                )[chunk.slice]
            )

        dask_arr = da.concatenate(chunks_darrs, axis=0)

        if labelled:
            # Dimension labels
            dims = ['trainId'] + ['dim_%d' % i for i in range(dask_arr.ndim - 1)]

            # Train ID index
            coords = {'trainId': self._trainid_index()}

            import xarray
            return xarray.DataArray(dask_arr, dims=dims, coords=coords)
        else:
            return dask_arr