import argparse

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from hercules import HerculesOutput


def plot_outputs(plot_individual_turbine_setpoints=True):
    dfs_herc = [
        HerculesOutput("outputs_ol/hercules_output.h5").df,
        HerculesOutput("outputs_cl/hercules_output.h5").df,
    ]
    dfs_ctrl = [
        pd.read_pickle("outputs_ol/controller_log.p"),
        pd.read_pickle("outputs_cl/controller_log.p"),
    ]

    labels = ["Open-loop control", "Closed-loop control"]

    n_turbines = 2
    pow_cols = ["wind_farm.turbine_powers.{0:03d}".format(t) for t in range(n_turbines)]
    ref_col = "external_signals.plant_power_reference"
    mod_ref_cols = [
        "wind_farm.turbine_power_setpoints.{0:03d}".format(t) for t in range(n_turbines)
    ]
    t_refs_pre_col = "wind_farm.turbine_power_setpoints_pre_limit"
    t_refs_post_col = "wind_farm.turbine_power_setpoints"
    colors = ["C0", "C1"]

    # Create plots
    fig, ax = plt.subplots(2, 1, sharex=True, sharey=True)
    fig.set_size_inches(10, 5)

    for case, (dfh, dfc, label) in enumerate(zip(dfs_herc, dfs_ctrl, labels)):
        # Extract data from larger array
        time = dfh["time"].to_numpy()
        powers = dfh[pow_cols].to_numpy()
        ref = dfh[ref_col].to_numpy()
        mod_ref = dfh[mod_ref_cols].to_numpy().sum(axis=1)

        t_refs_pre = np.stack(dfc[t_refs_pre_col].to_numpy())
        t_refs_post = np.stack(dfc[t_refs_post_col].to_numpy())

        # Direction
        for t in range(n_turbines):
            if t == 0:
                base = 0
            else:
                base = powers[:, :t].sum(axis=1)
            ax[case].fill_between(
                time,
                base,
                base + powers[:, t],
                label="T{0:03d} power".format(t),
                alpha=0.5,
                color=colors[t],
                edgecolor="None",
            )
            if plot_individual_turbine_setpoints:
                ax[case].plot(
                    time,
                    base + t_refs_pre[:, t],
                    label="T{0:03d} pre-limit setpoint".format(t),
                    color=colors[t],
                    linestyle="dashed",
                )
                ax[case].plot(
                    time,
                    base + t_refs_post[:, t],
                    label="T{0:03d} post-limit setpoint".format(t),
                    color=colors[t],
                    linestyle="dotted",
                )

        ax[case].plot(time, powers.sum(axis=1), color="black", label="Farm power")
        ax[case].plot(time, ref, color="gray", linestyle="dashed", label="Raw farm power reference")
        ax[case].plot(
            time, mod_ref, color="gray", linestyle="dotted", label="Ramp-limited farm reference"
        )

        # Plot aesthetics
        ax[case].grid()
        ax[case].set_title(label)
        ax[case].set_ylabel("Power [kW]")
    ax[0].set_xlim([time[0], time[-1]])
    ax[0].legend(loc="lower left")
    ax[1].set_xlabel("Time [s]")

    return fig


# In this example, the wind turbines are aligned with the oncoming wind, so T000 wakes T001.
# The farm power setpoint more than available to begin, so both
# turbines are at max power. Between 10s and 20s, the setpoint ramps down to 3000kW; the open-loop
# controller asks each turbine for 1500kW, but only the upstream turbine is able to meet the demand,
# so the total farm power is below the setpoint. The closed-loop controller is able to adjust the
# power of T000 to compensate for T001's underperformance, and the farm power tracks the setpoint.
# When the setpoint shifts to 2000kW, there is sufficient resource for T001 to produce 1000kW, and
# both controllers meet the setpoint.

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Plot outputs of battery market example")

    parser.add_argument(
        "--save_plots", type=bool, default=False, help="Whether to save the generated plots"
    )

    args = parser.parse_args()

    fig = plot_outputs(plot_individual_turbine_setpoints=False)

    if args.save_plots:
        fig.savefig("../../docs/graphics/wf-power-tracking-plot.png", dpi=300, format="png")

    plt.show()
