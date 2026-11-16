import copy
from abc import abstractmethod

from hycon.interfaces.interface_base import InterfaceBase


class HerculesInterfaceBase(InterfaceBase):
    """Shared implementation for the component-based Hercules interfaces."""

    available_controls = ("power_setpoint",)
    data_channel_map: dict[str, str]
    wind_types: list[str]
    solar_types: list[str]
    battery_types: list[str]
    hydrogen_types: list[str]
    thermal_types: list[str]
    playback_types: list[str]
    capacity_key: str
    battery_power_capacity_key: str
    battery_charge_rate_key: str
    battery_discharge_rate_key: str
    battery_soc_max_key: str
    battery_soc_min_key: str

    @abstractmethod
    def __init__(self, h_dict):
        super().__init__()
        self.dt = h_dict["dt"]

        if "plant" in h_dict and h_dict["plant"] is not None:
            self.plant_parameters = copy.deepcopy(h_dict["plant"])
        else:
            self.plant_parameters = {}

        self.component_names = h_dict["component_names"]
        self.component_types = {c: h_dict[c]["component_type"] for c in self.component_names}

        for c in self.component_names:
            c_type = self.component_types[c]
            if c_type in self.wind_types:
                self.plant_parameters[c] = {
                    "type": "wind",
                    "component_category": "generator",
                    "capacity": h_dict[c][self.capacity_key],
                    "n_turbines": h_dict[c]["n_turbines"],
                    "turbines": range(h_dict[c]["n_turbines"]),
                }
            elif c_type in self.solar_types:
                self.plant_parameters[c] = {
                    "type": "solar",
                    "component_category": "generator",
                    "capacity": h_dict[c][self.capacity_key],
                }
            elif c_type in self.battery_types:
                self.plant_parameters[c] = {
                    "type": "battery",
                    "component_category": "storage",
                    "power_capacity": h_dict[c][self.battery_power_capacity_key],
                    "energy_capacity": h_dict[c]["energy_capacity"],
                    "charge_rate": h_dict[c][self.battery_charge_rate_key],
                    "discharge_rate": h_dict[c][self.battery_discharge_rate_key],
                    "allow_grid_charging": h_dict[c].get("allow_grid_power_consumption", True),
                    "state_of_charge_max": h_dict[c].get(self.battery_soc_max_key, 1.0),
                    "state_of_charge_min": h_dict[c].get(self.battery_soc_min_key, 0.0),
                }
            elif c_type in self.hydrogen_types:
                self.plant_parameters[c] = {"type": "hydrogen", "component_category": "load"}
            elif c_type in self.thermal_types:
                self.plant_parameters[c] = {"type": "thermal", "component_category": "generator"}
            elif c_type in self.playback_types:
                self.plant_parameters[c] = {"type": "playback", "component_category": "generator"}
            else:
                raise ValueError(f"Component '{c}' has unrecognized type '{c_type}' for Hycon.")

        self._lmp_da_keys = tuple(f"lmp_da_{h:02d}" for h in range(24))

    def check_controls(self, controls_dict):
        super().check_controls(controls_dict)

    def get_measurements(self, h_dict):
        time = h_dict["time"]
        measurements = {
            "time": time,
            "forecast": {},
        }

        total_power = 0.0
        local_power = 0.0

        for c in h_dict["component_names"]:
            component_power = h_dict[c]["power"]
            total_power += component_power
            if self.plant_parameters[c]["component_category"] in ["generator", "storage"]:
                # TODO: Do we need another that excludes storage?
                local_power += component_power
            component_measurements = {"power": component_power}
            for k, v in self.data_channel_map.items():
                if k in h_dict[c]:
                    component_measurements[v] = h_dict[c][k]

            measurements[c] = component_measurements

        measurements["total_power"] = total_power
        measurements["local_power"] = local_power

        measurements["plant_power_reference"] = h_dict["external_signals"].get(
            "plant_power_reference", None
        )

        for c in h_dict["component_names"]:
            if self.component_types[c] in self.wind_types:
                measurements[c]["wind_directions"] = [
                    h_dict[c]["wind_direction_mean"]
                ] * self.plant_parameters[c]["n_turbines"]

        if "hydrogen_reference" in h_dict["external_signals"]:
            for c in h_dict["component_names"]:
                if self.component_types[c] in self.hydrogen_types:
                    measurements[c]["hydrogen_production_reference"] = h_dict["external_signals"][
                        "hydrogen_reference"
                    ]

        if "lmp_da_00" in h_dict["external_signals"]:
            measurements["DA_LMP_24hours"] = [
                h_dict["external_signals"][k] for k in self._lmp_da_keys
            ]
        measurements["DA_LMP"] = h_dict["external_signals"].get("lmp_da", None)
        measurements["RT_LMP"] = h_dict["external_signals"].get("lmp_rt", None)

        for k in h_dict["external_signals"].keys():
            if "forecast" in k:
                measurements["forecast"][k] = h_dict["external_signals"][k]

        # TODO: How to prescribe an override signal for one or more components?
        return measurements

    def send_controls(self, h_dict, controls_dict):
        controls_dict = copy.deepcopy(controls_dict)
        for c in self.component_names:
            if c in controls_dict:
                c_type = self.component_types[c]
                if c_type in self.wind_types:
                    if "power_setpoint" not in controls_dict[c]:
                        raise ValueError(
                            "Missing required control 'power_setpoint' for wind component "
                            + c
                            + "."
                        )
                    controls_dict[c]["turbine_power_setpoints"] = controls_dict[c].pop(
                        "power_setpoint"
                    )
                h_dict[c] = h_dict[c] | controls_dict[c]

        return h_dict


class HerculesV2Interface(HerculesInterfaceBase):
    """Class for interfacing with Hercules v2 simulator."""

    data_channel_map = {
        "power": "power",
        "power_reference": "power_reference",
        "soc": "state_of_charge",
        "turbine_powers": "turbine_powers",
        "turbine_speeds": "turbine_speeds",
        "wind_direction_mean": "wind_direction_mean",
        "dni": "direct_normal_irradiance",
        "aoi": "angle_of_incidence",
        "H2_mfr": "production_rate",
    }
    wind_types = ["WindFarm"]
    solar_types = ["SolarPySAMPVWatts"]
    battery_types = ["BatteryLithiumIon", "BatterySimple"]
    hydrogen_types = ["ElectrolyzerPlant"]
    thermal_types = ["HardCoalSteamTurbine", "OpenCycleGasTurbine"]
    playback_types = ["PowerPlayback"]
    capacity_key = "capacity"
    battery_power_capacity_key = "size"
    battery_charge_rate_key = "charge_rate"
    battery_discharge_rate_key = "discharge_rate"
    battery_soc_max_key = "max_SOC"
    battery_soc_min_key = "min_SOC"

    def __init__(self, h_dict):
        super().__init__(h_dict)


class HerculesV3Interface(HerculesInterfaceBase):
    """Class for interfacing with Hercules v3 simulator."""

    data_channel_map = {
        "power": "power",
        "power_hypothetical": "power_hypothetical",
        "power_reference": "power_reference",
        "SOC": "state_of_charge",
        "turbine_powers": "turbine_powers",
        "turbine_speeds": "turbine_speeds",
        "wind_direction_mean": "wind_direction_mean",
        "DNI": "direct_normal_irradiance",
        "AOI": "angle_of_incidence",
        "H2_MFR": "production_rate",
    }
    wind_types = ["WindFarm"]
    solar_types = ["SolarPySAMPVWatts"]
    battery_types = ["BatteryDynamic", "BatteryLithiumIon", "BatteryReservoir"]
    hydrogen_types = ["ElectrolyzerPlant"]
    thermal_types = [
        "CombinedCyclePlant",
        "LinearGenerator",
        "OpenCycleGasTurbine",
        "SteamTurbine",
    ]
    playback_types = ["PowerPlayback"]
    capacity_key = "capacity_rated"
    battery_power_capacity_key = "power_discharge_max"
    battery_charge_rate_key = "power_charge_max"
    battery_discharge_rate_key = "power_discharge_max"
    battery_soc_max_key = "SOC_max"
    battery_soc_min_key = "SOC_min"

    def __init__(self, h_dict):
        super().__init__(h_dict)


# Alias to the interface for the current Hercules release
HerculesInterface = HerculesV2Interface
