import numpy as np
import pandas as pd
import pytest
from hycon.controllers import (
    BatteryController,
    HybridSupervisoryControllerGeneric,
    SolarPassthroughController,
    WindFarmPowerDistributingController,
)
from hycon.controllers.controller_base import ControllerBase
from hycon.interfaces.interface_base import InterfaceBase


class PassthroughInterface(InterfaceBase):
    def __init__(self):
        super().__init__()
        self.dt = 1.0
        self.plant_parameters = {}

    def get_measurements(self, input_dict):
        return dict(input_dict)

    def check_controls(self, controls_dict):
        pass

    def send_controls(self, input_dict, controls_dict):
        return controls_dict


class LoggingController(ControllerBase):
    def __init__(self, interface):
        super().__init__(interface, cname="tagged")
        self.x = 0.0

    def set_controller_parameters(self):
        pass

    def compute_controls(self, measurements_dict):
        e = measurements_dict["ref"] - measurements_dict["y"]
        self.x += e
        self.store("x", self.x)
        self.store("e", e)
        self.store("vec", np.array([e, 2 * e]))
        return {"tagged": {"u": e}}


def test_log_stored_values(tmp_path):
    controller = LoggingController(PassthroughInterface())
    controller.step({"time": 0.0, "ref": 2.0, "y": 1.0})
    controller.step({"time": 1.0, "ref": 5.0, "y": 1.0})

    df = controller.get_log()
    assert list(df.columns) == ["time", "tagged.x", "tagged.e", "tagged.vec"]
    assert df["time"].tolist() == [0.0, 1.0]
    assert df["tagged.x"].tolist() == [1.0, 5.0]
    assert df["tagged.e"].tolist() == [1.0, 4.0]
    assert np.allclose(df["tagged.vec"].iloc[1], [4.0, 8.0])

    filename = tmp_path / "log.csv"
    controller.write_log(filename, output_type="csv")
    assert pd.read_csv(filename)["tagged.e"].tolist() == [1.0, 4.0]

    # Attributes alone do not produce rows once the stored values have been consumed.
    controller.x = 100.0
    controller.log(time=2.0)
    assert len(controller.get_log()) == 2


def test_log_discards_what_if_values():
    controller = LoggingController(PassthroughInterface())
    controller.compute_controls_without_updating_state({"ref": 100.0, "y": 0.0})
    controller.step({"time": 0.0, "ref": 2.0, "y": 1.0})
    controller.compute_controls_without_updating_state({"ref": 100.0, "y": 0.0})
    controller.step({"time": 1.0, "ref": 2.0, "y": 1.0})

    df = controller.get_log()
    assert df["tagged.e"].tolist() == [1.0, 1.0]
    assert df["tagged.x"].tolist() == [1.0, 2.0]


def test_log_component_controllers(test_hercules_dict, test_interface_hercules):
    wind = WindFarmPowerDistributingController(test_interface_hercules, "wind_farm")
    solar = SolarPassthroughController(test_interface_hercules, "solar_farm")
    battery = BatteryController(test_interface_hercules, "battery")
    supervisor = HybridSupervisoryControllerGeneric(
        test_interface_hercules,
        controller_parameters={"component_controllers": [wind, solar, battery]},
    )

    for t in [0.0, 1.0]:
        test_hercules_dict["time"] = t
        out = supervisor.step(test_hercules_dict)

    # Get component log
    df = battery.get_log()
    assert df["time"].tolist() == [0.0, 1.0]
    pd.testing.assert_frame_equal(
        supervisor.get_log()[
            ["time"] + [c for c in supervisor.get_log().columns if c.startswith("battery")]
        ],
        df,
    )
    assert list(df.columns) == [
        "time",
        "battery.internal_state",
        "battery.processed_reference_power",
        "battery.error",
        "battery.incremental_control",
    ]
    # Logged values come from the real call, not the supervisor's what-if query
    assert np.isclose(
        df["battery.error"].iloc[-1],
        df["battery.processed_reference_power"].iloc[-1] - test_hercules_dict["battery"]["power"],
    )
    assert np.isclose(
        out["battery"]["power_setpoint"],
        test_hercules_dict["battery"]["power"] + df["battery.incremental_control"].iloc[-1],
    )


def test_store_replaces_pending_value():
    controller = LoggingController(PassthroughInterface())
    controller.store("e", 1.0)
    controller.store("e", 2.0)
    assert controller.get_log().empty

    controller.log(time=0.0)
    assert controller.get_log().to_dict("records") == [{"time": 0.0, "tagged.e": 2.0}]

    controller.log(time=1.0)
    assert len(controller.get_log()) == 1


def test_get_log_combines_nested_controllers(tmp_path):
    interface = PassthroughInterface()
    supervisor = LoggingController(interface)
    supervisor.cname = "supervisor"
    component = LoggingController(interface)
    component.cname = "battery"
    nested = LoggingController(interface)
    nested.cname = "inner"
    supervisor.components = [component]
    component.nested_logger = nested

    supervisor.store("power", 10.0)
    component.store("power", 2.0)
    supervisor.log(time=0.0)
    component.store("power", 3.0)
    nested.store("power", 4.0)
    supervisor.log(time=1.0)
    supervisor.store("power", 20.0)
    supervisor.log(time=2.0)

    expected = pd.DataFrame(
        {
            "time": [0.0, 1.0, 2.0],
            "supervisor.power": [10.0, np.nan, 20.0],
            "battery.power": [2.0, 3.0, np.nan],
            "inner.power": [np.nan, 4.0, np.nan],
        }
    )
    pd.testing.assert_frame_equal(supervisor.get_log(), expected)
    filename = tmp_path / "combined.pkl"
    supervisor.write_log(filename)
    pd.testing.assert_frame_equal(pd.read_pickle(filename), expected)
    # Retrieving combined results does not modify individual caches.
    assert len(supervisor._log_cache) == 2
    assert list(component.get_log().columns) == ["time", "battery.power", "inner.power"]


def test_get_log_rejects_column_collisions():
    upper = LoggingController(PassthroughInterface())
    upper.lower = LoggingController(PassthroughInterface())
    upper.store("power", 1.0)
    upper.lower.store("power", 2.0)
    upper.log(time=0.0)
    with pytest.raises(ValueError, match="Duplicate log columns"):
        upper.get_log()


def test_get_log_rejects_ambiguous_timestamps():
    upper = LoggingController(PassthroughInterface())
    upper.lower = LoggingController(PassthroughInterface())
    upper.lower.cname = "lower"
    for _ in range(2):
        upper.store("power", 1.0)
        upper.lower.store("power", 2.0)
        upper.log(time=0.0)
    with pytest.raises(pd.errors.MergeError):
        upper.get_log()


def test_reset_log_clears_all_logs():
    interface = PassthroughInterface()
    supervisor = LoggingController(interface)
    supervisor.cname = "supervisor"
    component = LoggingController(interface)
    component.cname = "battery"
    supervisor.components = [component]

    supervisor.store("power", 10.0)
    component.store("power", 2.0)
    supervisor.log(time=0.0)
    supervisor.store("power", 12.0)
    # No log added to sub_logger, for test
    supervisor.log(time=1.0)

    assert len(supervisor.get_log()) == 2
    assert len(component.get_log()) == 1

    supervisor.reset_log()

    assert supervisor.get_log().empty
    assert component.get_log().empty


def test_sub_logger_discovery_does_not_scan_log_buffers():
    class UnscannableCache(list):
        def __iter__(self):
            raise AssertionError("Sub-logger discovery must not scan historical log rows.")

    upper = LoggingController(PassthroughInterface())
    lower = LoggingController(PassthroughInterface())
    upper.sub_logger = lower
    upper._log_cache = UnscannableCache([{"time": 0.0, "power": 1.0}] * 10000)
    lower._log_cache = UnscannableCache()
    upper.store("power", 2.0)
    lower.store("power", 3.0)

    assert upper._sub_loggers() == [lower]
    upper.log(time=1.0)
    assert len(upper._log_cache) == 10001
    assert len(lower._log_cache) == 1


def test_store_snapshots_mutable_values():
    controller = LoggingController(PassthroughInterface())
    array = np.array([1.0, 2.0])
    nested = {"values": [3.0]}
    controller.store("array", array)
    controller.store("nested", nested)
    controller.store("scalar", np.float32(4.0))
    array[0] = 100.0
    nested["values"].append(100.0)
    controller.log(time=0.0)

    row = controller.get_log().iloc[0]
    np.testing.assert_array_equal(row["tagged.array"], [1.0, 2.0])
    assert row["tagged.nested"] == {"values": [3.0]}
    assert row["tagged.scalar"] == np.float32(4.0)


def test_what_if_preserves_cache_and_restores_pending_values():
    class UncopyableCache(list):
        def __deepcopy__(self, memo):
            raise AssertionError("Hypothetical calculations must not copy log history.")

    controller = LoggingController(PassthroughInterface())
    controller._log_cache = UncopyableCache()
    cache = controller._log_cache
    controller.store("pending", np.array([1.0]))
    for _ in range(3):
        controller.compute_controls_without_updating_state({"ref": 100.0, "y": 0.0})
        assert controller.x == 0.0
        assert controller._log_cache is cache
        assert "_initial_state" not in controller.__dict__
        assert list(controller._log_row) == ["pending"]
        np.testing.assert_array_equal(controller._log_row["pending"], [1.0])


def test_what_if_restores_state_on_error():
    class FailingController(LoggingController):
        def compute_controls(self, measurements_dict):
            self.x = 100.0
            self.store("error", 100.0)
            raise ValueError("Calculation failed")

    controller = FailingController(PassthroughInterface())
    controller.store("pending", 1.0)
    with pytest.raises(ValueError, match="Calculation failed"):
        controller.compute_controls_without_updating_state({})
    assert controller.x == 0.0
    assert controller._log_row == {"pending": 1.0}


def test_what_if_does_not_copy_sub_logger_caches_and_restores_in_place():
    class UncopyableCache(list):
        def __deepcopy__(self, memo):
            raise AssertionError("Hypothetical calculations must not copy log history.")

    class StatefulSupervisor(LoggingController):
        def compute_controls(self, measurements_dict):
            for sub_logger in self.components:
                sub_logger.compute_controls(measurements_dict)
            self.x += 1.0
            return {}

    interface = PassthroughInterface()
    supervisor = StatefulSupervisor(interface)
    supervisor.cname = "supervisor"
    battery = LoggingController(interface)
    battery.cname = "battery"
    nested = LoggingController(interface)
    nested.cname = "nested"
    supervisor.components = [battery]
    battery.nested_logger = nested

    for logger in (supervisor, battery, nested):
        logger._log_cache = UncopyableCache([{"time": 0.0, "power": 1.0}])
    caches = [logger._log_cache for logger in (supervisor, battery, nested)]
    battery.store("pending", 5.0)

    supervisor.compute_controls_without_updating_state({"ref": 2.0, "y": 0.0})

    # Object identity is preserved, so external references stay valid.
    assert supervisor.components[0] is battery
    assert battery.nested_logger is nested
    # Caches are the original objects, untouched.
    assert [logger._log_cache for logger in (supervisor, battery, nested)] == caches
    assert all(
        logger._log_cache is cache for logger, cache in zip((supervisor, battery, nested), caches)
    )
    # State of every logger in the tree is restored, including pending values.
    assert supervisor.x == 0.0
    assert battery.x == 0.0
    assert battery._log_row == {"pending": 5.0}
    assert supervisor._log_row == {}

    # Subsequent logging reaches the original objects.
    battery.store("power", 2.0)
    supervisor.log(time=1.0)
    assert len(battery._log_cache) == 2


def test_logging_handles_cycles_and_shared_sub_loggers():
    interface = PassthroughInterface()
    supervisor = LoggingController(interface)
    supervisor.cname = "supervisor"
    battery = LoggingController(interface)
    battery.cname = "battery"
    supervisor.components = [battery]
    supervisor.battery = battery  # Same sub-logger reachable twice
    battery.parent = supervisor  # Back-reference creates a cycle

    supervisor.store("power", 10.0)
    battery.store("power", 2.0)
    supervisor.log(time=0.0)
    battery.store("power", 3.0)
    supervisor.log(time=1.0)

    assert len(battery._log_cache) == 2
    expected = pd.DataFrame(
        {
            "time": [0.0, 1.0],
            "supervisor.power": [10.0, np.nan],
            "battery.power": [2.0, 3.0],
        }
    )
    pd.testing.assert_frame_equal(supervisor.get_log(), expected)
    # Starting from the sub-logger reaches the supervisor through the back-reference.
    assert set(battery.get_log().columns) == set(expected.columns)

    battery.reset_log()
    assert supervisor.get_log().empty
