"""
Main driver of MindlessGen.
"""

from __future__ import annotations

import multiprocessing as mp
import warnings

from ..molecules import generate_random_molecule, Molecule
from ..qm import XTB, get_xtb_path, QMMethod, ORCA, get_orca_path
from ..molecules import iterative_optimization, postprocess_mol
from ..prog import ConfigManager

from .. import __version__


def generator(config: ConfigManager) -> tuple[list[Molecule] | None, int]:
    """
    Generate a molecule.
    """

    #  ______             _
    # |  ____|           (_)
    # | |__   _ __   __ _ _ _ __   ___
    # |  __| | '_ \ / _` | | '_ \ / _ \
    # | |____| | | | (_| | | | | |  __/)
    # |______|_| |_|\__, |_|_| |_|\___|
    #                __/ |
    #               |___/

    if config.general.verbosity > 0:
        print(header(str(__version__)))

    if config.general.print_config:
        print(config)
        return None, 0

    # Import and set up required engines
    refine_engine: QMMethod = setup_engines(
        config.refine.engine, config, get_xtb_path, get_orca_path
    )

    if config.general.postprocess:
        postprocess_engine: QMMethod | None = setup_engines(
            config.postprocess.engine, config, get_xtb_path, get_orca_path
        )
    else:
        postprocess_engine = None

    if config.general.verbosity > 0:
        print(config)

    # lower number of the available cores and the configured parallelism
    num_cores = min(mp.cpu_count(), config.general.parallel)
    if config.general.parallel > mp.cpu_count():
        warnings.warn(
            f"Number of cores requested ({config.general.parallel}) is greater "
            + f"than the number of available cores ({mp.cpu_count()})."
            + f"Using {num_cores} cores instead."
        )
    if config.general.verbosity > 0:
        print(f"Running with {num_cores} cores.")

    if num_cores > 1 and config.general.verbosity > 0:
        # raise warning that parallelization will disable verbosity
        warnings.warn(
            "Parallelization will disable verbosity during iterative search. "
            + "Set '--verbosity 0' or '-P 1' to avoid this warning, or simply ignore it."
        )

    optimized_molecules: list[Molecule] = []
    for molcount in range(config.general.num_molecules):
        manager = mp.Manager()
        stop_event = manager.Event()
        cycles = range(config.general.max_cycles)
        backup_verbosity: int | None = None
        if num_cores > 1 and config.general.verbosity > 0:
            backup_verbosity = (
                config.general.verbosity
            )  # Save verbosity level for later
            config.general.verbosity = 0  # Disable verbosity if parallel

        if config.general.verbosity == 0:
            print("Cycle... ", end="", flush=True)
        with mp.Pool(processes=num_cores) as pool:
            results = pool.starmap(
                single_molecule_generator,
                [
                    (config, refine_engine, postprocess_engine, cycle, stop_event)
                    for cycle in cycles
                ],
            )
        if config.general.verbosity == 0:
            print("")

        # Restore verbosity level if it was changed
        if backup_verbosity is not None:
            config.general.verbosity = backup_verbosity

        # Filter out None values and return the first successful molecule
        optimized_molecule: Molecule | None = None
        for i, result in enumerate(results):
            if result is not None:
                cycles_needed = i + 1
                optimized_molecule = result
                break

        if optimized_molecule is None:
            raise RuntimeError(
                f"Molecule generation including optimization (and postprocessing) failed for all cycles for molecule {molcount + 1}."
            )
        if config.general.verbosity > 0:
            print(f"\nOptimized mindless molecule found in {cycles_needed} cycles.")
            print(optimized_molecule)
        optimized_molecules.append(optimized_molecule)

    return optimized_molecules, 0


def single_molecule_generator(
    config: ConfigManager,
    refine_engine: QMMethod,
    postprocess_engine: QMMethod | None,
    cycle: int,
    stop_event,
):
    """
    Generate a single molecule.
    """
    if stop_event.is_set():
        return None  # Exit early if a molecule has already been found

    if config.general.verbosity == 0:
        # print the cycle in one line, not starting a new line
        print("✔", end="", flush=True)
    elif config.general.verbosity > 0:
        print(f"Cycle {cycle + 1}:")
    #   _____                           _
    #  / ____|                         | |
    # | |  __  ___ _ __   ___ _ __ __ _| |_ ___  _ __
    # | | |_ |/ _ \ '_ \ / _ \ '__/ _` | __/ _ \| '__|
    # | |__| |  __/ | | |  __/ | | (_| | || (_) | |
    #  \_____|\___|_| |_|\___|_|  \__,_|\__\___/|_|

    mol = generate_random_molecule(config.generate, config.general.verbosity)

    try:
        #    ____        _   _           _
        #   / __ \      | | (_)         (_)
        #  | |  | |_ __ | |_ _ _ __ ___  _ _______
        #  | |  | | '_ \| __| | '_ ` _ \| |_  / _ \
        #  | |__| | |_) | |_| | | | | | | |/ /  __/
        #   \____/| .__/ \__|_|_| |_| |_|_/___\___|
        #         | |
        #         |_|
        optimized_molecule = iterative_optimization(
            mol=mol,
            engine=refine_engine,
            config_generate=config.generate,
            config_refine=config.refine,
            verbosity=config.general.verbosity,
        )
    except RuntimeError as e:
        if config.general.verbosity > 0:
            print(f"Refinement failed for cycle {cycle + 1}.")
            if config.general.verbosity > 1:
                print(e)
        return None

    if config.general.postprocess:
        try:
            optimized_molecule = postprocess_mol(
                optimized_molecule,
                postprocess_engine,  # type: ignore
                config.postprocess,
                config.general.verbosity,
            )
        except RuntimeError as e:
            if config.general.verbosity > 0:
                print(f"Postprocessing failed for cycle {cycle + 1}.")
                if config.general.verbosity > 1:
                    print(e)
            return None

    if not stop_event.is_set():
        stop_event.set()  # Signal other processes to stop
        if config.general.verbosity > 1:
            print("Postprocessing successful. Optimized molecule:")
        return optimized_molecule
    else:
        return None


def header(version: str) -> str:
    """
    This function prints the header of the program.
    """
    headerstr = (
        # pylint: disable=C0301
        "╔══════════════════════════════════════════════════════════════════════════════════════════════════╗\n"
        "║                                                                                                  ║\n"
        "║   ███╗   ███╗██╗███╗   ██╗██████╗ ██╗     ███████╗███████╗███████╗ ██████╗ ███████╗███╗   ██╗    ║\n"
        "║   ████╗ ████║██║████╗  ██║██╔══██╗██║     ██╔════╝██╔════╝██╔════╝██╔════╝ ██╔════╝████╗  ██║    ║\n"
        "║   ██╔████╔██║██║██╔██╗ ██║██║  ██║██║     █████╗  ███████╗███████╗██║  ███╗█████╗  ██╔██╗ ██║    ║\n"
        "║   ██║╚██╔╝██║██║██║╚██╗██║██║  ██║██║     ██╔══╝  ╚════██║╚════██║██║   ██║██╔══╝  ██║╚██╗██║    ║\n"
        "║   ██║ ╚═╝ ██║██║██║ ╚████║██████╔╝███████╗███████╗███████║███████║╚██████╔╝███████╗██║ ╚████║    ║\n"
        "║   ╚═╝     ╚═╝╚═╝╚═╝  ╚═══╝╚═════╝ ╚══════╝╚══════╝╚══════╝╚══════╝ ╚═════╝ ╚══════╝╚═╝  ╚═══╝    ║\n"
        "║                                                                                                  ║\n"
        f"║                                       MindlessGen v{version[:5]}                                         ║\n"
        "║                                 Semi-Automated Molecule Generator                                ║\n"
        "║                                                                                                  ║\n"
        "║                          Licensed under the Apache License, Version 2.0                          ║\n"
        "║                           (http://www.apache.org/licenses/LICENSE-2.0)                           ║\n"
        "╚══════════════════════════════════════════════════════════════════════════════════════════════════╝"
    )
    return headerstr


# Define a utility function to set up the required engine
def setup_engines(
    engine_type: str,
    engine_config: ConfigManager,
    xtb_path_func,
    orca_path_func,
):
    """
    Set up the required engine.
    """
    if engine_type == "xtb":
        try:
            path = xtb_path_func(engine_config.xtb.xtb_path)
            if not path:
                raise ImportError("xtb not found.")
        except ImportError as e:
            raise ImportError("xtb not found.") from e
        return XTB(path)
    elif engine_type == "orca":
        try:
            path = orca_path_func(engine_config.orca.orca_path)
            if not path:
                raise ImportError("orca not found.")
        except ImportError as e:
            raise ImportError("orca not found.") from e
        return ORCA(path)
    else:
        raise NotImplementedError("Engine not implemented.")
