"""Compatibility imports for the Hercules v3 interface."""

from hycon.interfaces.hercules_interface import HerculesV3Interface as HerculesV3Interface

hercules_data_channel_map = HerculesV3Interface.data_channel_map
hercules_wind_types = HerculesV3Interface.wind_types
hercules_solar_types = HerculesV3Interface.solar_types
hercules_battery_types = HerculesV3Interface.battery_types
hercules_hydrogen_types = HerculesV3Interface.hydrogen_types
hercules_thermal_types = HerculesV3Interface.thermal_types
hercules_playback_types = HerculesV3Interface.playback_types
