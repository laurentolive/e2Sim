"""e2sim command line: python e2sim_cli.py <command> ... (exit code 0 ok, 1 fail, 2 error)."""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from . import toolchains


def cmd_fs(args) -> int:
    if args.op == "stamp":  # stamp FILE TEXT: written only when TEXT changes (make dependency on options)
        p, text = Path(args.paths[0]), " ".join(args.paths[1:])
        if not p.is_file() or p.read_text(encoding="utf-8") != text:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text, encoding="utf-8")
        return 0
    for p in map(Path, args.paths):
        if args.op == "mkdir":
            p.mkdir(parents=True, exist_ok=True)
        elif p.is_dir():
            shutil.rmtree(p)
        elif p.exists():
            p.unlink()
    return 0


def sdk_root() -> Path:
    """Directory of target/ and mk/: the repository when run from it, else <prefix>/share/e2sim (pip)."""
    repo = Path(__file__).resolve().parent.parent
    if (repo / "mk" / "e2sim.mk").is_file():
        return repo
    share = Path(sys.prefix) / "share" / "e2sim"
    if (share / "mk" / "e2sim.mk").is_file():
        return share
    raise toolchains.ToolchainError("e2Sim SDK (target/, mk/) not found")


def cmd_coverage(args) -> int:
    from . import coverage, pe

    build = Path(args.build)
    reg = toolchains.load(Path(args.registry) if args.registry else None)
    dll = next(iter(sorted(build.glob("*.dll")) + sorted(build.glob("*.so"))), None)
    tc = reg.by_arch(pe.read(dll).arch) if dll else reg.get(args.toolchain)
    cov = coverage.collect(build, tc.tool("gcov"), Path(args.sources) if args.sources else None)
    if not cov:
        print(f"e2sim: no coverage data (*.gcda) in {build}: build with COVERAGE=1 and run the tests")
        return 1
    root = Path(args.sources).resolve() if args.sources else None
    print(coverage.summary(cov, root))
    if args.html:
        coverage.write_html(cov, Path(args.html))
        print(f"e2sim: report {Path(args.html) / 'index.html'}")
    return 0


def cmd_extract(args) -> int:
    from . import extract

    if bool(args.make) == bool(args.compdb):
        print("e2sim: --make or --compdb expected", file=sys.stderr)
        return 2
    compiles = (extract.from_make(args.make, Path(args.cwd)) if args.make
                else extract.from_compdb(Path(args.compdb)))
    out = Path(args.out)
    text = extract.make_fragment(compiles, args.name, out.parent, exclude=args.exclude or [],
                                 adapter=[Path(a) for a in args.adapter or []], drop_defines=args.drop_define or [])
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    print(text.splitlines()[0])
    print(f"e2sim: {out}")
    return 0


def cmd_root(args) -> int:
    print(sdk_root().as_posix())
    return 0


def cmd_toolchain(args) -> int:
    reg = toolchains.load(Path(args.registry) if args.registry else None)
    if args.op == "list":
        for name, tc in reg.toolchains.items():
            print(f"{name:12} {tc.arch:7} {tc.prefix}" + ("  (default)" if name == reg.default else ""))
        print(f"registry: {reg.file}")
        return 0
    tc = reg.get(args.name)
    out = Path(args.dir) / f"toolchain-{tc.name}.mk"
    out.parent.mkdir(parents=True, exist_ok=True)
    text = toolchains.make_fragment(tc, reg)
    if not out.is_file() or out.read_text(encoding="utf-8") != text:
        out.write_text(text, encoding="utf-8")
    print(out.as_posix())
    return 0


def _run_args(p):
    p.add_argument("board", help="board.yaml or system.yaml")
    p.add_argument("--toolchain", help="toolchain of the build to run (default: registry default)")


def _license() -> str:
    """Licence procedure before a simulation (never blocks it, spec §17)."""
    from .license import check_at_startup

    text = check_at_startup()
    print(f"e2sim: {text}", flush=True)
    return text


def cmd_license(args) -> int:
    import webbrowser

    from .license import LicenseManager, product
    from .license.ui import make_ui

    ui = make_ui()
    try:
        mgr = LicenseManager(ui)
        if args.action == "choose":
            if mgr.license is not None and not mgr.license.is_expired:
                print("e2sim: the current license is valid; 'e2sim license activate' enters a Professional key")
            else:
                mgr.ensure()
        elif args.action == "activate":
            mgr.activate(args.key)
        elif args.action == "deactivate":
            mgr.deactivate()
        elif args.action == "check":
            ok = mgr.revalidate(silent=False)
            if ok is False and (mgr.license is None or mgr.license.type.value != "Professional"):
                print("e2sim: no Professional license to validate")
        elif args.action == "buy":
            webbrowser.open(product.BUY_URL)
            print(f"e2sim: {product.BUY_URL}")
        elif args.action == "portal":
            webbrowser.open(product.PORTAL_URL)
            print(f"e2sim: {product.PORTAL_URL}")
        print(f"e2sim: {mgr.status_text()}")
        lic = mgr.license
        if lic is not None and lic.type.value == "Professional" and lic.customer_email:
            print(f"e2sim: licensed to {lic.customer_email}, last validated {lic.last_validated_utc:%Y-%m-%d %H:%M} UTC")
    finally:
        ui.close()
    return 0


def cmd_run(args) -> int:
    from .sim import Sim

    _license()

    with Sim(args.board, toolchain=args.toolchain, connect=args.connect) as sim:
        if args.connect:
            print(f"e2sim: waiting for the firmware on 127.0.0.1:{args.connect} ...", flush=True)
        sim.start()
        for st in sim.instances:
            if st.escope is not None:
                print(f"e2sim: {st.name}: eScope on TCP:127.0.0.1,{st.escope.port} "
                      f"(protocol V3, {st.inst.ptr_size * 8} bits addresses, symbols {st.inst.dll.name})", flush=True)
            for p in st.ports.values():
                if p.relay is not None:
                    print(f"e2sim: {st.name}.{p.name} on TCP:127.0.0.1,{p.relay.port}", flush=True)
        if args.power_on:
            sim.power_on()
        if args.duration is not None:
            sim.run(s=args.duration)
        else:
            print("e2sim: running in real time, Ctrl+C to stop", flush=True)
            try:
                sim.run_realtime()
            except KeyboardInterrupt:
                pass
        for name in args.snapshot or []:
            port, _, file = name.partition("=")
            sim[port].save_png(file or f"{port}.png")
            print(f"e2sim: {port} -> {file or port + '.png'}")
        print(f"e2sim: stopped at t = {sim.now:.6f} s")
    return 0


def cmd_gui(args) -> int:
    from .gui import Gui
    from .sim import Sim

    license_text = _license()  # dialogs before the firmware and the page
    with Sim(args.board, toolchain=args.toolchain) as sim:
        gui = Gui(sim, port=args.port)
        gui.license = license_text
        sim.start()
        if args.power_on:
            sim.power_on()
        for st in sim.instances:
            if st.escope is not None:
                print(f"e2sim: {st.name}: eScope on TCP:127.0.0.1,{st.escope.port}", flush=True)
        print(f"e2sim: GUI on http://127.0.0.1:{args.port}/  (Ctrl+C to stop)", flush=True)
        try:
            gui.serve(open_browser=not args.no_browser)
        except KeyboardInterrupt:
            pass
    return 0


def cmd_replay(args) -> int:
    from .sim import replay

    _license()

    sim, same = replay(args.record, toolchain=args.toolchain, connect=args.connect)
    print(f"e2sim: replayed {args.record} up to t = {sim.now:.6f} s: "
          + ("same outputs as recorded" if same else "OUTPUTS DIFFER from the record"))
    return 0 if same else 1


def main(argv: list[str] | None = None) -> int:
    from . import __version__

    ap = argparse.ArgumentParser(prog="e2sim", description="e2Sim - firmware simulation on PC")
    ap.add_argument("--version", action="version", version=f"e2sim {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("coverage", help="coverage of the firmware (build COVERAGE=1, then the tests)")
    p.add_argument("build", help="build directory of the DLLs (build/<toolchain>)")
    p.add_argument("--sources", help="keep the sources under this directory only")
    p.add_argument("--html", help="HTML report directory")
    p.add_argument("--toolchain")
    p.add_argument("--registry")
    p.set_defaults(func=cmd_coverage)

    p = sub.add_parser("extract", help="sources / includes / defines of the target build -> make fragment for e2Sim")
    p.add_argument("--make", help='target build command, run in dry mode (-n -B -w), e.g. "make -C ../firmware"')
    p.add_argument("--compdb", help="compile_commands.json of the target build")
    p.add_argument("--cwd", default=".", help="directory of the --make command")
    p.add_argument("--exclude", action="append", help='glob of sources / includes to drop, e.g. "*/Hw/MCU/*"')
    p.add_argument("--adapter", action="append", help="directory of the e2Sim HAL adapter (sources added)")
    p.add_argument("--drop-define", action="append", help="define to drop (name)")
    p.add_argument("--name", required=True, help="firmware name (DLL)")
    p.add_argument("--out", default="e2sim_sources.mk")
    p.set_defaults(func=cmd_extract)

    p = sub.add_parser("root", help="directory of the SDK (target/, mk/): E2SIM_ROOT of the makefiles")
    p.set_defaults(func=cmd_root)

    p = sub.add_parser("fs", help="portable file operations for the makefiles")
    p.add_argument("op", choices=["mkdir", "rm", "stamp"])
    p.add_argument("paths", nargs="+")
    p.set_defaults(func=cmd_fs)

    p = sub.add_parser("toolchain", help="toolchains (e2sim_toolchains.yaml)")
    p.add_argument("op", choices=["list", "mk"])
    p.add_argument("name", nargs="?", help="toolchain name (mk; default: 'default:' of the file)")
    p.add_argument("--dir", default="build", help="mk: output directory")
    p.add_argument("--registry", help="e2sim_toolchains.yaml (default: search, spec §10.1)")
    p.set_defaults(func=cmd_toolchain)

    p = sub.add_parser("run", help="run a simulation (headless: --duration)")
    _run_args(p)
    p.add_argument("--duration", type=float, help="virtual seconds to run in max speed, then stop")
    p.add_argument("--snapshot", action="append", metavar="PORT[=file.png]", help="save a framebuffer at the end")
    p.add_argument("--connect", type=int, metavar="PORT", help="do not launch the firmware: wait for it (debugger)")
    p.add_argument("--power-on", action="store_true", help="power the firmware at start (power latch boards)")
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("license", help="show or manage the license (Demonstration, Personal, Professional)")
    p.add_argument("action", nargs="?", default="status",
                   choices=["status", "choose", "activate", "deactivate", "check", "buy", "portal"])
    p.add_argument("key", nargs="?", help="Professional license key (activate)")
    p.set_defaults(func=cmd_license)

    p = sub.add_parser("gui", help="web GUI of the simulation (real time, run / pause / step / speed)")
    _run_args(p)
    p.add_argument("--port", type=int, default=8080)
    p.add_argument("--power-on", action="store_true", help="power the firmware at start (power latch boards)")
    p.add_argument("--no-browser", action="store_true")
    p.set_defaults(func=cmd_gui)

    p = sub.add_parser("replay", help="send a record (.e2simrec) again, check the outputs are the same")
    p.add_argument("record")
    p.add_argument("--toolchain")
    p.add_argument("--connect", type=int, metavar="PORT", help="wait for the runner launched by the debugger")
    p.set_defaults(func=cmd_replay)

    p = sub.add_parser("connect", help="wait for a firmware launched from the debugger, run in real time")
    _run_args(p)
    p.add_argument("--port", type=int, default=47600)
    p.add_argument("--power-on", action="store_true", help="power the firmware at start (power latch boards)")
    p.set_defaults(func=lambda a: cmd_run(argparse.Namespace(board=a.board, toolchain=a.toolchain, duration=None,
                                                              snapshot=None, connect=a.port, power_on=a.power_on)))

    args = ap.parse_args(argv)
    try:
        return args.func(args)
    except toolchains.ToolchainError as e:
        print(f"e2sim: {e}", file=sys.stderr)
        return 2
    except Exception as e:  # noqa: BLE001 - CLI boundary
        from .sim import SimError

        if isinstance(e, SimError):
            print(f"e2sim: {e}", file=sys.stderr)
            return 2
        raise
