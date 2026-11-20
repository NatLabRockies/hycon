import pandas as pd
import pytest
from hycon.interfaces import HerculesInterface, HerculesV2Interface, HerculesV3Interface


@pytest.fixture(
    params=[
        pytest.param(
            (HerculesV2Interface, "test_hercules_v2_dict", "capacity", "size", "soc"), id="v2"
        ),
        pytest.param(
            (
                HerculesV3Interface,
                "test_hercules_v3_dict",
                "capacity_rated",
                "power_discharge_max",
                "SOC",
            ),
            id="v3",
        ),
    ]
)
def hercules_case(request):
    interface_class, fixture_name, capacity_key, battery_capacity_key, soc_key = request.param
    return (
        interface_class,
        request.getfixturevalue(fixture_name),
        capacity_key,
        battery_capacity_key,
        soc_key,
    )


def test_HerculesInterface_alias():
    assert HerculesInterface is HerculesV2Interface


def test_hercules_interface_windonly(hercules_case):
    interface_class, hercules_dict, capacity_key, _, _ = hercules_case
    hercules_dict["component_names"] = ["wind_farm"]
    interface = interface_class(h_dict=hercules_dict)
    assert interface.dt == hercules_dict["dt"]
    assert (
        interface.plant_parameters["wind_farm"]["capacity"]
        == (hercules_dict["wind_farm"][capacity_key])
    )
    assert (
        interface.plant_parameters["wind_farm"]["n_turbines"]
        == (hercules_dict["wind_farm"]["n_turbines"])
    )

    measurements = interface.get_measurements(h_dict=hercules_dict)
    assert measurements["time"] == hercules_dict["time"]
    assert (
        measurements["wind_farm"]["wind_directions"]
        == [hercules_dict["wind_farm"]["wind_direction_mean"]] * 2
    )
    assert (
        measurements["wind_farm"]["turbine_powers"]
        == (hercules_dict["wind_farm"]["turbine_powers"])
    )
    assert measurements["forecast"] == {
        k: v for k, v in hercules_dict["external_signals"].items() if "forecast" in k
    }

    controls_dict = {"wind_farm": {"power_setpoint": [2000.0, 3000.0]}}
    bad_controls_dict = {
        "wind_farm": {
            "wind_power_setpoint": [2000.0, 3000.0],
            "unavailable_control": [0.0, 0.0],
        }
    }
    interface.check_controls(controls_dict)
    with pytest.raises(ValueError):
        interface.check_controls(bad_controls_dict)

    result = interface.send_controls(hercules_dict, controls_dict)
    assert (
        controls_dict["wind_farm"]["power_setpoint"]
        == (result["wind_farm"]["turbine_power_setpoints"])
    )
    with pytest.raises(TypeError):
        interface.send_controls(hercules_dict, **bad_controls_dict)


def test_hercules_interface_hybrid(hercules_case):
    interface_class, hercules_dict, capacity_key, battery_capacity_key, soc_key = hercules_case
    interface = interface_class(h_dict=hercules_dict)
    assert interface.dt == hercules_dict["dt"]
    assert (
        interface.plant_parameters["wind_farm"]["capacity"]
        == (hercules_dict["wind_farm"][capacity_key])
    )
    assert (
        interface.plant_parameters["solar_farm"]["capacity"]
        == (hercules_dict["solar_farm"][capacity_key])
    )
    assert (
        interface.plant_parameters["battery"]["power_capacity"]
        == (hercules_dict["battery"][battery_capacity_key])
    )
    assert (
        interface.plant_parameters["battery"]["energy_capacity"]
        == (hercules_dict["battery"]["energy_capacity"])
    )
    assert (
        interface.plant_parameters["wind_farm"]["n_turbines"]
        == (hercules_dict["wind_farm"]["n_turbines"])
    )

    measurements = interface.get_measurements(h_dict=hercules_dict)
    assert measurements["time"] == hercules_dict["time"]
    assert (
        measurements["wind_farm"]["wind_directions"]
        == [hercules_dict["wind_farm"]["wind_direction_mean"]] * 2
    )
    assert (
        measurements["wind_farm"]["turbine_powers"]
        == (hercules_dict["wind_farm"]["turbine_powers"])
    )
    assert measurements["solar_farm"]["power"] == hercules_dict["solar_farm"]["power"]
    assert measurements["battery"]["power"] == hercules_dict["battery"]["power"]
    assert measurements["battery"]["state_of_charge"] == hercules_dict["battery"][soc_key]

    controls_dict = {
        "wind_farm": {"power_setpoint": [2000.0, 3000.0]},
        "solar_farm": {"power_setpoint": 500.0},
        "battery": {"power_setpoint": -1000.0},
    }
    bad_controls_dict = {
        "wind_farm": {"power_setpoint": [2000.0, 3000.0]},
        "solar_farm": {"power_setpoint": 500.0},
        "battery": {"unavailable_control": [0.0, 0.0]},
    }
    interface.check_controls(controls_dict)
    with pytest.raises(ValueError):
        interface.check_controls(bad_controls_dict)

    result = interface.send_controls(hercules_dict, controls_dict)
    assert (
        controls_dict["wind_farm"]["power_setpoint"]
        == (result["wind_farm"]["turbine_power_setpoints"])
    )
    assert controls_dict["solar_farm"]["power_setpoint"] == (result["solar_farm"]["power_setpoint"])
    assert controls_dict["battery"]["power_setpoint"] == result["battery"]["power_setpoint"]
    assert (
        interface.plant_parameters["interconnect_limit"]
        == (hercules_dict["plant"]["interconnect_limit"])
    )


def test_v3_hypothetical_solar_power(test_hercules_v3_dict):
    interface = HerculesV3Interface(h_dict=test_hercules_v3_dict)
    measurements = interface.get_measurements(h_dict=test_hercules_v3_dict)
    assert (
        measurements["solar_farm"]["power_hypothetical"]
        == (test_hercules_v3_dict["solar_farm"]["power_hypothetical"])
    )


def test_v3_LMP_keys_and_time_utc(test_hercules_v3_dict):
    # The v3 interface reads uppercase LMP signals and adds time_utc when starttime_utc is set.
    h_dict = test_hercules_v3_dict
    h_dict["time"] = 3600.0
    h_dict["starttime_utc"] = pd.Timestamp("2024-01-01T00:00Z")
    h_dict["external_signals"].update(
        {"LMP_RT": 20.0, "LMP_DA": 30.0, **{f"LMP_DA_{h:02d}": float(h) for h in range(24)}}
    )
    measurements = HerculesV3Interface(h_dict).get_measurements(h_dict)
    assert measurements["RT_LMP"] == 20.0
    assert measurements["DA_LMP"] == 30.0
    assert measurements["DA_LMP_24hours"] == [float(h) for h in range(24)]
    assert measurements["time_utc"] == pd.Timestamp("2024-01-01T01:00Z")
