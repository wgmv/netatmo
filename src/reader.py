"""reader.py
Data reader for Netatmo weather station data files.
"""

import os
from formatters import NetatmoConsoleFormatter
import utils


class DataReader:
    """Reads and provides access to stored weather data."""
    
    def __init__(self, filepath):
        """
        Args:
            filepath: Path to the JSON data file
        """
        self.filepath = filepath
    
    def exists(self):
        return os.path.isfile(self.filepath)
    
    def read(self):
        """
        Returns:
            Dictionary containing the data, or empty dict if file doesn't exist
        """
        if self.exists():
            return utils.read_json(self.filepath)
        return {}
    
    def display(self, formatter):
        """        
        Args:
            formatter: A formatter object with a format() method
            
        Returns:
            Formatted string, or None if no data
        """
        data = self.read()
        return formatter.format(data)
    
if __name__ == '__main__':
    reader = DataReader("data/data.json")
    formatter = NetatmoConsoleFormatter()
    print(reader.display(formatter))

