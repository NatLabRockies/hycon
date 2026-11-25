import numpy as np
import pandas as pd
from hycon.controllers.battery_controller_peak_locked_arbitrage import (
    BatteryControllerPeakLockedArbitrage,
)
from hycon.interfaces import HerculesV3Interface


def make_controller(h_dict, tmp_path):
    """Peak-locked controller with peak blocks at 12:00 on 2024-01-01 and 2024-01-02."""
    h_dict["battery"]["roundtrip_efficiency"] = 0.9
    peaks = pd.DataFrame({"time_utc": pd.to_datetime(["2024-01-01T12:00Z", "2024-01-02T12:00Z"])})
    peaks.to_feather(tmp_path / "peaks.ftr")
    return BatteryControllerPeakLockedArbitrage(
        HerculesV3Interface(h_dict),
        "battery",
        controller_parameters={
            "load_peak_forecast_filename": str(tmp_path / "peaks.ftr"),
            "discharge_margin": 5.0,
        },
    )


def test_peak_locked_logs_offers_in_peak(test_hercules_v3_dict, tmp_path):
    # In peak the battery offers rated power in DA and RT. The DA offer price is the
    # cheapest replacement price (10 $/MWh) / 0.9 + 5, so a 50 $/MWh DA LMP clears it.
    controller = make_controller(test_hercules_v3_dict, tmp_path)
    measurements = {
        "time_utc": pd.Timestamp("2024-01-01T13:00Z"),
        "RT_LMP": 0.0,
        "DA_LMP": 50.0,
        "DA_LMP_24hours": [10.0] * 24,
        "battery": {"state_of_charge": 0.9},
    }
    controls = controller.compute_controls(measurements)
    controller.log(0.0)
    log = controller.get_log().iloc[0]

    assert list(controls["battery"]) == ["power_setpoint"]
    assert log["battery.in_peak"] == 1
    assert log["battery.offer_DA"] == 10e3
    assert log["battery.offer_RT"] == 10e3
    assert np.isclose(log["battery.offer_price_DA"], 10.0 / 0.9 + 5.0)
    assert log["battery.power_cleared_DA"] == 10e3


def test_peak_locked_logs_offers_off_peak(test_hercules_v3_dict, tmp_path):
    # Off peak there is no DA offer or clearing; the RT offer is the power the usable
    # SOC can sustain for 5 minutes, capped at rated power.
    controller = make_controller(test_hercules_v3_dict, tmp_path)
    measurements = {
        "time_utc": pd.Timestamp("2024-01-01T06:00Z"),
        "RT_LMP": 0.0,
        "DA_LMP": 50.0,
        "DA_LMP_24hours": [10.0] * 24,
        "battery": {"state_of_charge": 0.5},
    }
    controller.compute_controls(measurements)
    controller.log(0.0)
    log = controller.get_log().iloc[0]

    assert log["battery.in_peak"] == 0
    assert log["battery.RT_available"] == 1
    assert log["battery.offer_DA"] == 0.0
    assert np.isnan(log["battery.offer_price_DA"])
    assert log["battery.power_cleared_DA"] == 0.0
    assert log["battery.offer_RT"] == 10e3
    assert log["battery.power_charge_from_excess"] == 0.0
