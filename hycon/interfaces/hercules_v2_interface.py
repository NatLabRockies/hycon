"""Compatibility imports for the Hercules v2 interface."""

from hycon.interfaces.hercules_interface import HerculesV2Interface as HerculesV2Interface

hercules_data_channel_map = HerculesV2Interface.data_channel_map
hercules_wind_types = HerculesV2Interface.wind_types
hercules_solar_types = HerculesV2Interface.solar_types
hercules_battery_types = HerculesV2Interface.battery_types
hercules_hydrogen_types = HerculesV2Interface.hydrogen_types
hercules_thermal_types = HerculesV2Interface.thermal_types
hercules_playback_types = HerculesV2Interface.playback_types
