"""formatter.py
Formatters for Netatmo weather station data display.
"""

import utils


class NetatmoConsoleFormatter:
    """Formats Netatmo weather data for console display."""

    def format(self, data):
        """Format weather data as a console string.
        
        Args:
            data: Netatmo API response data
            
        Returns:
            Formatted string for console output, or None if no data
        """
        if "body" not in data:
            return None
        
        parts = [f"Time {utils.timestr(data['time_server'])}"]
        device = data["body"]["devices"][0]
        
        # Add device data
        parts.extend(self._format_device_data(device))
        
        # Add module data
        for module in device.get("modules", []):
            parts.extend(self._format_module_data(module))
        
        return " | ".join(parts)

    def _format_device_data(self, device):
        """Format main device sensor data."""
        parts = []
        dashboard = device.get("dashboard_data", {})
        
        if "Pressure" in dashboard:
            parts.append(f"Pressure {dashboard['Pressure']}")
        if "Temperature" in dashboard:
            parts.append(f"Indoor {dashboard['Temperature']}")
        
        return parts

    def _format_module_data(self, module):
        """Format module sensor data based on module type."""
        if "dashboard_data" not in module:
            return []
        
        module_type = module["type"]
        dashboard = module["dashboard_data"]
        
        formatters = {
            "NAModule1": self._format_outdoor,
            "NAModule2": self._format_wind,
            "NAModule3": self._format_rain,
            "NAModule4": self._format_optional_indoor,
        }
        
        formatter = formatters.get(module_type)
        return formatter(module, dashboard) if formatter else []

    def _format_outdoor(self, module, dashboard):
        """Format outdoor module data."""
        if "Temperature" in dashboard:
            return [f"Outdoor {dashboard['Temperature']}"]
        return []

    def _format_wind(self, module, dashboard):
        """Format wind gauge data."""
        parts = []
        if "WindStrength" in dashboard:
            wind_str = f"Wind {dashboard['WindStrength']}"
            if "WindAngle" in dashboard:
                wind_str += f" angle {dashboard['WindAngle']}"
            parts.append(wind_str)
        return parts

    def _format_rain(self, module, dashboard):
        """Format rain gauge data."""
        if "Rain" in dashboard:
            return [f"Rain {dashboard['Rain']}"]
        return []

    def _format_optional_indoor(self, module, dashboard):
        """Format optional indoor module data."""
        module_name = module.get("module_name", "Opt Indoor")
        if "Temperature" in dashboard:
            return [f"{module_name} {dashboard['Temperature']}"]
        return []
