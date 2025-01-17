from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import List
    from typing import Optional

    from datetime import datetime

    import pandas as pd

    from .query import QueryData
    from .result_reader_writer.result_reader import ColumnMode

    from .result_network import ResultCatchments
    from .result_network import ResultNodes
    from .result_network import ResultReaches
    from .result_network import ResultStructures
    from .result_network import ResultGlobalDatas

import os.path

from .dotnet import from_dotnet_datetime
from .dotnet import to_dotnet_datetime
from .dotnet import to_numpy

from .result_extractor import ExtractorCreator
from .result_extractor import ExtractorOutputFileType
from .result_network import ResultNetwork
from .result_reader_writer import ResultMerger
from .result_reader_writer import ResultReaderCreator
from .result_reader_writer import ResultReaderType
from .result_reader_writer import ResultWriter

from .query import QueryDataCatchment  # noqa: F401
from .query import QueryDataNode  # noqa: F401
from .query import QueryDataReach  # noqa: F401
from .query import QueryDataStructure  # noqa: F401
from .query import QueryDataGlobal  # noqa: F401

from .result_query.query_data_converter import QueryDataConverter

from .various import mike1d_quantities  # noqa: F401
from .various import NAME_DELIMITER
from .various import make_list_if_not_iterable

from .quantities import TimeSeriesId

from .pandas_extension import Mikeio1dAccessor  # noqa: F401

from System import DateTime


class Res1D:
    """
    Class for reading data from 1D network result files into Pandas data frame.
    Currently supported formats are:

    * MIKE 1D network and catchment res1d files
    * MIKE 1D Long Term Statistics res1d files
    * MOUSE legacy PRF and CRF files
    * EPANET res and resx files generated by MIKE+
    * SWMM out files

    Parameters
    ----------
    file_path : str
        Relative or absolute path of the relevant result file.
    lazy_load : bool
        Flag specifying to load the file using lazy loading bridge of MIKE 1D.
        This typically is useful if only a few time steps need to be read for the whole network.
    header_load : bool
        Flag specifying to load just a header of the result file.
    reaches : list of str
        Filter list of reach ID strings, which will be included when loading the result file.
    nodes : list of str
        Filter list of node ID strings, which will be included when loading the result file.
    catchments : list of str
        Filter list of catchment ID strings, which will be included when loading the result file.
    col_name_delimiter : str
        String to delimit the quantity ID with location ID
        (and optionally chainage) in the data frame label.
    put_chainage_in_col_name : bool
        Flag specifying to add chainage into data frame column label.
    clear_queries_after_reading : bool
        Flag specifying to clear active queries after reading/processing them.

    Examples
    --------
    An example of reading the res1d file only for nodes with
    ID 'node1', 'node2' and reaches with ID 'reach1', 'reach2':

    >>> nodes = ['node1', 'node2']
    >>> reaches = ['reach1', 'reach2']
    >>> res1d = Res1D('MyRes1D.res1d', nodes=nodes, reaches=reaches)
    >>> res1d.read()
    """

    def __init__(
        self,
        file_path=None,
        lazy_load=False,
        header_load=False,
        reaches=None,
        nodes=None,
        catchments=None,
        col_name_delimiter=NAME_DELIMITER,
        put_chainage_in_col_name=True,
        clear_queue_after_reading=True,
        result_reader_type=ResultReaderType.COPIER,
    ):
        self.result_reader = ResultReaderCreator.create(
            result_reader_type,
            self,
            file_path,
            lazy_load,
            header_load,
            reaches,
            nodes,
            catchments,
            col_name_delimiter,
            put_chainage_in_col_name,
        )

        self._start_time = None
        self._end_time = None

        self.result_network = ResultNetwork(self)
        self.network = self.result_network
        self.result_writer = ResultWriter(self)

        self.clear_queue_after_reading = clear_queue_after_reading

        self.network = self.result_network  # alias
        """Network of the result file."""
        self.catchments = self.result_network.catchments
        """Catchments of the result file."""
        self.reaches: ResultReaches = self.result_network.reaches
        """Reaches of the result file."""
        self.nodes = self.result_network.nodes
        """Nodes of the result file."""
        self.structures = self.result_network.structures
        """Structures of the result file."""
        self.global_data = self.result_network.global_data
        """Global data of the result file."""

    def __repr__(self):
        return "<mikeio1d.Res1D>"

    def _get_info(self) -> info:
        info = []
        if self.file_path:
            info.append(f"Start time: {str(self.start_time)}")
            info.append(f"End time: {str(self.end_time)}")
            info.append(f"# Timesteps: {str(self.data.NumberOfTimeSteps)}")
            info.append(f"# Catchments: {self.data.Catchments.get_Count()}")
            info.append(f"# Nodes: {self.data.Nodes.get_Count()}")
            info.append(f"# Reaches: {self.data.Reaches.get_Count()}")

            info.append(f"# Globals: {self.data.GlobalData.DataItems.Count}")
            for i, quantity in enumerate(self.data.Quantities):
                info.append(f"{i} - {quantity.Id} <{quantity.EumQuantity.UnitAbbreviation}>")

        info = str.join("\n", info)
        return info

    # region Private methods

    def info(self):
        """Prints information about the result file."""
        info = self._get_info()
        print(info)

    def _get_timeseries_ids_to_read(
        self, queries: List[QueryData] | List[TimeSeriesId]
    ) -> List[TimeSeriesId]:
        """Find out which list of TimeSeriesId objects should be used for reading.

        If user supplies queries, then convert them to TimeSeriesId. Otherwise use the
        current queue of TimeSeriesId objects.

        Parameters
        ----------
        queries : List[QueryData] | List[TimeSeriesId]
            List of queries or time series ids supplied in read() method.

        Returns
        -------
        List of TimeSeriesId objects.
        """
        queries = make_list_if_not_iterable(queries)

        if queries is None or len(queries) == 0:
            return self.result_network.queue

        is_already_time_series_ids = isinstance(queries[0], TimeSeriesId)
        if is_already_time_series_ids:
            return queries

        queries = QueryDataConverter.convert_queries_to_time_series_ids(self, queries)
        return queries

    # endregion Private methods

    def read(
        self,
        queries: Optional[List[QueryData] | QueryData | List[TimeSeriesId] | TimeSeriesId] = None,
        column_mode: Optional[str | ColumnMode] = None,
    ) -> pd.DataFrame:
        """
        Read loaded .res1d file data based on queries.
        Currently the supported query classes are

        * :class:`query.QueryDataNode`
        * :class:`query.QueryDataReach`
        * :class:`query.QueryDataCatchment`

        Parameters
        ----------
        queries: A single query or a list of queries.
            Default is None = reads all data.
        column_mode : str | ColumnMode (optional)
            Specifies the type of column index of returned DataFrame.
            'all' - column MultiIndex with levels matching TimeSeriesId objects.
            'compact' - same as 'all', but removes levels with default values.
            'timeseries' - column index of TimeSeriesId objects
            'str' - column index of str representations of QueryData objects

        Returns
        -------
        pd.DataFrame

        Examples
        --------
        An example of reading res1d file with queries:

        >>> res1d = Res1D('MyRes1D.res1d')
        >>> queries = [
                QueryDataNode('WaterLevel', 'node1'),
                QueryDataReach('Discharge', 'reach1', 50.0)
            ]
        >>> res1d.read(queries)
        """

        timeseries_ids = self._get_timeseries_ids_to_read(queries)

        if len(timeseries_ids) == 0:
            return self.read_all(column_mode=column_mode)

        df = self.result_reader.read(timeseries_ids, column_mode=column_mode)

        if self.clear_queue_after_reading:
            self.clear_queue()

        return df

    def read_all(self, column_mode: Optional[str | ColumnMode] = None) -> pd.DataFrame:
        """Read all data from res1d file to dataframe.

        Parameters
        ----------
        column_mode : str | ColumnMode (optional)
            Specifies the type of column index of returned DataFrame.
            'all' - column MultiIndex with levels matching TimeSeriesId objects.
            'compact' - same as 'all', but removes levels with default values.
            'timeseries' - column index of TimeSeriesId objects
            'str' - column index of str representations of QueryData objects

        Returns
        -------
        pd.DataFrame
        """
        return self.result_reader.read_all(column_mode=column_mode)

    def clear_queue(self):
        """Clear the current active list of queries."""
        self.result_network.queue.clear()

    @property
    def time_index(self) -> pd.DatetimeIndex:
        """pandas.DatetimeIndex of the time index."""
        return self.result_reader.time_index

    @property
    def start_time(self) -> datetime:
        """Start time of the result file."""
        if self._start_time is not None:
            return self._start_time

        return from_dotnet_datetime(self.data.StartTime)

    @property
    def end_time(self) -> datetime:
        """End time of the result file."""
        if self._end_time is not None:
            return self._end_time

        return from_dotnet_datetime(self.data.EndTime)

    @property
    def quantities(self) -> List[str]:
        """Quantities in res1d file."""
        return self.result_reader.quantities

    @property
    def query(self):
        """
        .NET object ResultDataQuery to use for querying the loaded res1d data.

        More information about ResultDataQuery class see:
        https://manuals.mikepoweredbydhi.help/latest/General/Class_Library/DHI_MIKE1D/html/T_DHI_Mike1D_ResultDataAccess_ResultDataQuery.htm
        """
        return self.result_reader.query

    @property
    def searcher(self):
        """
        .NET object ResultDataSearcher to use for searching res1d data items on network.

        More information about ResultDataSearcher class see:
        https://manuals.mikepoweredbydhi.help/latest/General/Class_Library/DHI_MIKE1D/html/T_DHI_Mike1D_ResultDataAccess_ResultDataQuery.htm
        """
        return self.result_reader.searcher

    @property
    def file_path(self):
        """File path of the result file."""
        return self.result_reader.file_path

    @property
    def data(self):
        """
        .NET object ResultData with the loaded res1d data.

        More information about ResultData class see:
        https://manuals.mikepoweredbydhi.help/latest/General/Class_Library/DHI_MIKE1D/html/T_DHI_Mike1D_ResultDataAccess_ResultData.htm
        """
        return self.result_reader.data

    @property
    def projection_string(self):
        """Projection string of the result file."""
        return self.data.ProjectionString

    # region Query wrappers

    def get_catchment_values(self, catchment_id, quantity):
        return to_numpy(self.query.GetCatchmentValues(catchment_id, quantity))

    def get_node_values(self, node_id, quantity):
        return to_numpy(self.query.GetNodeValues(node_id, quantity))

    def get_reach_values(self, reach_name, chainage, quantity):
        return to_numpy(self.query.GetReachValues(reach_name, chainage, quantity))

    def get_reach_value(self, reach_name, chainage, quantity, time):
        if self.result_reader.is_lts_result_file():
            raise NotImplementedError("The method is not implemented for LTS event statistics.")

        time_dotnet = time if isinstance(time, DateTime) else to_dotnet_datetime(time)
        return self.query.GetReachValue(reach_name, chainage, quantity, time_dotnet)

    def get_reach_start_values(self, reach_name, quantity):
        return to_numpy(self.query.GetReachStartValues(reach_name, quantity))

    def get_reach_end_values(self, reach_name, quantity):
        return to_numpy(self.query.GetReachEndValues(reach_name, quantity))

    def get_reach_sum_values(self, reach_name, quantity):
        return to_numpy(self.query.GetReachSumValues(reach_name, quantity))

    # endregion Query wrapper

    def modify(self, data_frame: pd.DataFrame, file_path=None):
        """
        Modifies the ResultData object TimeData based on the provided data frame.

        Parameters
        ----------
        data_frame : pandas.DataFrame
            Pandas data frame object with column names based on query labels
        file_path : str
            File path for the new res1d file. Optional.
        """
        self.result_writer.modify(data_frame)
        if file_path is not None:
            self.save(file_path)

    def save(self, file_path):
        """
        Saves the ResultData to a new res1d file.

        Parameters
        ----------
        file_path : str
            File path for the new res1d file.
        """
        self.data.Connection.FilePath.Path = file_path
        self.data.Save()

    def extract(
        self,
        file_path,
        queries: Optional[List[QueryData] | QueryData | List[TimeSeriesId] | TimeSeriesId] = None,
        time_step_skipping_number=1,
        ext=None,
    ):
        """
        Extract given queries to provided file.
        File type is determined from file_path extension.
        The supported formats are:
        * csv
        * dfs0
        * txt

        Parameters
        ----------
        file_path : str
            Output file path.
        queries : list
            List of queries.
        time_step_skipping_number : int
            Number specifying the time step frequency to output.
        ext : str
            Output file type to use instead of determining it from extension.
            Can be 'csv', 'dfs0', 'txt'.
        """
        ext = os.path.splitext(file_path)[-1] if ext is None else ext

        timeseries_ids = self._get_timeseries_ids_to_read(queries)
        data_entries = [t.to_data_entry(self) for t in timeseries_ids]

        extractor = ExtractorCreator.create(
            ext, file_path, data_entries, self.data, time_step_skipping_number
        )
        extractor.export()

        if self.clear_queue_after_reading:
            self.clear_queue()

    def to_csv(
        self,
        file_path,
        queries: Optional[List[QueryData] | QueryData | List[TimeSeriesId] | TimeSeriesId] = None,
        time_step_skipping_number=1,
    ):
        """Extract to csv file."""
        self.extract(file_path, queries, time_step_skipping_number, ExtractorOutputFileType.CSV)

    def to_dfs0(
        self,
        file_path,
        queries: Optional[List[QueryData] | QueryData | List[TimeSeriesId] | TimeSeriesId] = None,
        time_step_skipping_number=1,
    ):
        """Extract to dfs0 file."""
        self.extract(file_path, queries, time_step_skipping_number, ExtractorOutputFileType.DFS0)

    def to_txt(
        self,
        file_path,
        queries: Optional[List[QueryData] | QueryData | List[TimeSeriesId] | TimeSeriesId] = None,
        time_step_skipping_number=1,
    ):
        """Extract to txt file."""
        self.extract(file_path, queries, time_step_skipping_number, ExtractorOutputFileType.TXT)

    @staticmethod
    def merge(file_names: List[str] | List[Res1D], merged_file_name: str):
        """
        Merges res1d files.

        It is possible to merge three kinds of result files:
        * Regular res1d (HD, RR, etc.)
        * LTS extreme statistics
        * LTS chronological statistics

        For regular res1d files the requirement is that the simulation start time
        of the first file matches the simulation end time of the second file
        (the same principle for subsequent files).

        For LTS result files, meaningful merged result file is obtained when
        simulation periods for the files do not overlap.

        Parameters
        ----------
        file_names : list of str or Res1D objects
            List of res1d file names to merge.
        merged_file_name : str
            File name of the res1d file to store the merged data.
        """
        file_names = Res1D._convert_res1d_to_str_for_file_names(file_names)
        result_merger = ResultMerger(file_names)
        result_merger.merge(merged_file_name)

    @staticmethod
    def _convert_res1d_to_str_for_file_names(file_names: List[str] | List[Res1D]):
        file_names_new = []
        for i in range(len(file_names)):
            entry = file_names[i]
            file_name = entry.file_path if isinstance(entry, Res1D) else entry
            file_names_new.append(file_name)
        return file_names_new
