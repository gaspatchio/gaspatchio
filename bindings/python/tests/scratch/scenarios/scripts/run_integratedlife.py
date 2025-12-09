"""
Enhanced IntegratedLife Model Runner

Runs the IntegratedLife model with flexible filtering of model points and scenarios,
comprehensive output generation, and detailed performance metrics.
"""
import argparse
import os
import re
import sys
import time
import tracemalloc
from datetime import datetime
from pathlib import Path

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False


def get_memory_usage():
    """
    Get current memory usage in bytes.
    Returns dict with 'tracemalloc' and optionally 'process' memory.
    """
    current, peak = tracemalloc.get_traced_memory()
    result = {
        'tracemalloc_current': current,
        'tracemalloc_peak': peak,
    }

    if HAS_PSUTIL:
        process = psutil.Process()
        mem_info = process.memory_info()
        result['process_rss'] = mem_info.rss  # Resident Set Size
        result['process_vms'] = mem_info.vms  # Virtual Memory Size

    return result


def format_memory(bytes_val):
    """Format bytes as human-readable memory string."""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes_val < 1024:
            return f"{bytes_val:.1f} {unit}"
        bytes_val /= 1024
    return f"{bytes_val:.1f} TB"


def parse_ids(spec_string):
    """
    Parse "1-5,8,10" or "all" into list of IDs.

    Args:
        spec_string: String like "1-5,8,10" or "all"

    Returns:
        "all" or list of integers
    """
    if spec_string.lower() == "all":
        return "all"

    ids = []
    try:
        for part in spec_string.split(','):
            part = part.strip()
            if '-' in part:
                start, end = map(int, part.split('-'))
                ids.extend(range(start, end + 1))
            else:
                ids.append(int(part))
        return sorted(set(ids))  # Remove duplicates
    except ValueError as e:
        raise ValueError(f"Invalid ID format '{spec_string}'. Use ranges (1-5) or lists (1,5,10)") from e


def parse_file(filepath):
    """
    Read IDs from file, one per line, skip empty lines and comments.

    Args:
        filepath: Path to file with IDs

    Returns:
        List of integers
    """
    if not Path(filepath).exists():
        raise FileNotFoundError(f"File not found: {filepath}")

    ids = []
    with open(filepath) as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if line and not line.startswith('#'):
                try:
                    ids.append(int(line))
                except ValueError:
                    raise ValueError(f"Invalid ID '{line}' at line {line_num} in {filepath}")
    return ids


def filter_results(results_dict, model_points, scenarios, verbose=False):
    """
    Filter result DataFrames by model points and scenarios.

    Args:
        results_dict: Dictionary of result DataFrames
        model_points: "all" or list of model point IDs
        scenarios: "all" or list of scenario IDs
        verbose: Whether to print filtering info

    Returns:
        Dictionary of filtered DataFrames
    """
    if model_points == "all" and scenarios == "all":
        return results_dict

    filtered = {}
    for name, df in results_dict.items():
        if verbose:
            print(f"  Filtering {name}...")

        # Results typically have point_id and scen as index or columns
        # We'll try to filter by index first, then columns
        try:
            if model_points != "all":
                if 'point_id' in df.index.names:
                    df = df.loc[df.index.get_level_values('point_id').isin(model_points)]
                elif 'point_id' in df.columns:
                    df = df[df['point_id'].isin(model_points)]

            if scenarios != "all":
                # Check for both 'scen' and 'scen_id' as the name might vary
                if 'scen' in df.index.names:
                    df = df.loc[df.index.get_level_values('scen').isin(scenarios)]
                elif 'scen_id' in df.index.names:
                    df = df.loc[df.index.get_level_values('scen_id').isin(scenarios)]
                elif 'scen' in df.columns:
                    df = df[df['scen'].isin(scenarios)]
                elif 'scen_id' in df.columns:
                    df = df[df['scen_id'].isin(scenarios)]
        except Exception as e:
            if verbose:
                print(f"    Warning: Could not filter {name}: {e}")

        filtered[name] = df

    return filtered


def save_results(results_dict, output_dir, format_type, verbose=False):
    """
    Save results to files in specified format.

    Args:
        results_dict: Dictionary of result DataFrames
        output_dir: Output directory path
        format_type: "csv", "parquet", or "both"
        verbose: Whether to print save progress

    Returns:
        List of (filename, size_bytes) tuples
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    saved_files = []

    for name, df in results_dict.items():
        if format_type in ["csv", "both"]:
            csv_path = output_path / f"{name}.csv"
            if verbose:
                print(f"  Saving {csv_path.name}...")
            df.to_csv(csv_path)
            saved_files.append((csv_path.name, csv_path.stat().st_size))

        if format_type in ["parquet", "both"]:
            parquet_path = output_path / f"{name}.parquet"
            if verbose:
                print(f"  Saving {parquet_path.name}...")
            df.to_parquet(parquet_path)
            saved_files.append((parquet_path.name, parquet_path.stat().st_size))

    return saved_files


def format_bytes(bytes_val):
    """Format bytes as human-readable string."""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes_val < 1024:
            return f"{bytes_val:.1f} {unit}"
        bytes_val /= 1024
    return f"{bytes_val:.1f} TB"


def format_time(seconds):
    """Format seconds as human-readable string."""
    if seconds < 1:
        return f"{seconds*1000:.0f}ms"
    elif seconds < 60:
        return f"{seconds:.1f}s"
    else:
        mins = int(seconds / 60)
        secs = seconds % 60
        return f"{mins}m {secs:.1f}s"


def main():
    parser = argparse.ArgumentParser(
        description="Run IntegratedLife model with flexible filtering and comprehensive outputs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run all model points and scenarios (both products)
  python run_integratedlife.py

  # Run only GMXB product
  python run_integratedlife.py --products gmxb

  # Run specific model points and scenarios
  python run_integratedlife.py --model-points 1-3,5,8 --scenarios 1-10

  # Run from files
  python run_integratedlife.py --model-points-file points.txt --scenarios-file scenarios.txt

  # Verbose mode with parquet output
  python run_integratedlife.py --verbose --format parquet --products gmxb

  # Run with single scenario (deterministic comparison mode)
  python run_integratedlife.py --num-scenarios 1 --products gmxb --verbose

  # Run with 8-point model points for Gaspatchio comparison
  python run_integratedlife.py --run-id 2 --num-scenarios 1 --products gmxb --verbose
        """
    )

    parser.add_argument('--model-points', type=str, default='all',
                        help='Model points to run (e.g., "1-5,8,10" or "all")')
    parser.add_argument('--model-points-file', type=str,
                        help='File with model point IDs (one per line)')
    parser.add_argument('--scenarios', type=str, default='all',
                        help='Scenarios to run (e.g., "1-100" or "all")')
    parser.add_argument('--scenarios-file', type=str,
                        help='File with scenario IDs (one per line)')
    parser.add_argument('--products', type=str, default='gmxb,glwb',
                        help='Products to run: "gmxb", "glwb", or "gmxb,glwb" (default: gmxb,glwb)')
    parser.add_argument('--format', type=str, default='csv', choices=['csv', 'parquet', 'both'],
                        help='Output format (default: csv)')
    parser.add_argument('--output-dir', type=str,
                        help='Output directory (default: appliedlife/output/{timestamp})')
    parser.add_argument('--verbose', action='store_true',
                        help='Enable detailed progress reporting')
    parser.add_argument('--num-scenarios', type=int, default=None,
                        help='Number of stochastic scenarios to generate (default: 100). '
                             'Use 1 for deterministic mode for comparison with Gaspatchio.')
    parser.add_argument('--run-id', type=int, default=1,
                        help='Run ID from run_params (default: 1). '
                             'Use 2 for 8-point 2023Q4IF model points.')

    args = parser.parse_args()

    # Parse products
    products_to_run = [p.strip().lower() for p in args.products.split(',')]
    valid_products = {'gmxb', 'glwb'}
    invalid_products = set(products_to_run) - valid_products
    if invalid_products:
        print(f"Error: Invalid products {invalid_products}. Must be 'gmxb', 'glwb', or 'gmxb,glwb'", file=sys.stderr)
        return 1

    # Parse model points and scenarios
    try:
        if args.model_points_file:
            model_points = parse_file(args.model_points_file)
        else:
            model_points = parse_ids(args.model_points)

        if args.scenarios_file:
            scenarios = parse_file(args.scenarios_file)
        else:
            scenarios = parse_ids(args.scenarios)
    except (ValueError, FileNotFoundError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    # Set up output directory
    if args.output_dir:
        output_dir = Path(args.output_dir)
    else:
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        script_dir = Path(__file__).parent
        output_dir = script_dir.parent / "output" / timestamp

    # Change to model directory
    script_dir = Path(__file__).parent
    model_dir = script_dir.parent / "ref" / "appliedlife"

    if not model_dir.exists():
        print(f"Error: Model directory not found: {model_dir}", file=sys.stderr)
        return 1

    os.chdir(model_dir)

    # Patch scen_size in source file BEFORE loading model (modelx caches on load)
    scenarios_file = model_dir / "IntegratedLife" / "Scenarios" / "__init__.py"
    original_scen_size_line = None
    if args.num_scenarios is not None and scenarios_file.exists():
        content = scenarios_file.read_text()
        # Find and replace the scen_size function
        pattern = r'(def scen_size\(\):\s*"""[^"]*"""\s*return )\d+'
        match = re.search(pattern, content)
        if match:
            original_scen_size_line = match.group(0)
            new_content = re.sub(pattern, f'\\g<1>{args.num_scenarios}', content)
            scenarios_file.write_text(new_content)
            if args.verbose:
                print(f"Patched {scenarios_file.name}: scen_size() returns {args.num_scenarios}")

    # Start memory tracking
    tracemalloc.start()
    memory_snapshots = {'start': get_memory_usage()}

    if args.verbose:
        print(f"Changed working directory to: {model_dir}")
        print(f"Output directory: {output_dir}")
        print(f"Run ID: {args.run_id}")
        print(f"Model points: {model_points if model_points != 'all' else 'all'}")
        print(f"Scenarios filter: {scenarios if scenarios != 'all' else 'all'}")
        if args.num_scenarios is not None:
            print(f"Stochastic scenarios: {args.num_scenarios} (patched)")
        print()

    # Track timing
    timings = {}
    start_time = time.time()

    # Load model
    if args.verbose:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Loading model...")

    load_start = time.time()
    try:
        import modelx as mx
        model = mx.read_model("IntegratedLife")
    except Exception as e:
        print(f"Error loading model: {e}", file=sys.stderr)
        return 1

    timings['model_load'] = time.time() - load_start
    memory_snapshots['model_load'] = get_memory_usage()

    if args.verbose:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Model loaded ({format_time(timings['model_load'])})")
        if args.num_scenarios is not None:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Using {args.num_scenarios} scenario(s)")

    # Create run
    run = model.Run[args.run_id]

    # Execute calculations
    results = {}
    calculations = []

    if 'gmxb' in products_to_run:
        calculations.extend([
            ('gmxb_pv', 'GMXB present values', lambda: run.GMXB.result_pv()),
            ('gmxb_cf', 'GMXB cashflows', lambda: run.GMXB.result_cf()),
            ('gmxb_pols', 'GMXB policy counts', lambda: run.GMXB.result_pols()),
        ])

    if 'glwb' in products_to_run:
        calculations.extend([
            ('glwb_pv', 'GLWB present values', lambda: run.GLWB.result_pv()),
            ('glwb_cf', 'GLWB cashflows', lambda: run.GLWB.result_cf()),
            ('glwb_pols', 'GLWB policy counts', lambda: run.GLWB.result_pols()),
        ])

    for calc_name, calc_desc, calc_func in calculations:
        if args.verbose:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Running {calc_desc}...")

        calc_start = time.time()
        try:
            results[calc_name] = calc_func()
        except Exception as e:
            print(f"Error running {calc_desc}: {e}", file=sys.stderr)
            return 1

        timings[calc_name] = time.time() - calc_start
        memory_snapshots[calc_name] = get_memory_usage()

        if args.verbose:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] {calc_desc.capitalize()} complete ({format_time(timings[calc_name])})")

    # Capture final memory snapshot
    memory_snapshots['final'] = get_memory_usage()

    # Filter results
    if args.verbose and (model_points != "all" or scenarios != "all"):
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Filtering results...")

    filter_start = time.time()
    results = filter_results(results, model_points, scenarios, args.verbose)
    timings['filtering'] = time.time() - filter_start

    # Determine actual counts for metrics
    # Try to infer from first result DataFrame
    first_result = next(iter(results.values()))
    try:
        if model_points == "all":
            if 'point_id' in first_result.index.names:
                num_points = first_result.index.get_level_values('point_id').nunique()
            elif 'point_id' in first_result.columns:
                num_points = first_result['point_id'].nunique()
            else:
                num_points = "unknown"
        else:
            num_points = len(model_points)

        if scenarios == "all":
            if 'scen' in first_result.index.names:
                num_scenarios = first_result.index.get_level_values('scen').nunique()
            elif 'scen_id' in first_result.index.names:
                num_scenarios = first_result.index.get_level_values('scen_id').nunique()
            elif 'scen' in first_result.columns:
                num_scenarios = first_result['scen'].nunique()
            elif 'scen_id' in first_result.columns:
                num_scenarios = first_result['scen_id'].nunique()
            else:
                num_scenarios = "unknown"
        else:
            num_scenarios = len(scenarios)
    except:
        num_points = len(model_points) if model_points != "all" else "unknown"
        num_scenarios = len(scenarios) if scenarios != "all" else "unknown"

    # Save results
    if args.verbose:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Saving results to {output_dir}/")

    save_start = time.time()
    saved_files = save_results(results, output_dir, args.format, args.verbose)
    timings['saving'] = time.time() - save_start

    # Calculate total execution time
    total_time = time.time() - start_time
    calc_time = sum(t for k, t in timings.items() if k.startswith(('gmxb_', 'glwb_')))

    # Generate run summary
    mode_str = "DETERMINISTIC" if args.num_scenarios == 1 else "STOCHASTIC"
    summary_lines = [
        "IntegratedLife Model Run",
        "=" * 50,
        f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"Run ID: {args.run_id}",
        f"Mode: {mode_str}" + (f" ({args.num_scenarios} scenario)" if args.num_scenarios == 1 else ""),
        f"Products: {', '.join([p.upper() for p in products_to_run])}",
        f"Model Points: {args.model_points if not args.model_points_file else f'file: {args.model_points_file}'} ({num_points} points)",
        f"Scenarios: {args.scenarios if not args.scenarios_file else f'file: {args.scenarios_file}'} ({num_scenarios} scenarios)",
    ]

    if isinstance(num_points, int) and isinstance(num_scenarios, int):
        total_projections = num_points * num_scenarios
        summary_lines.append(f"Total Projections: {total_projections} ({num_points} points × {num_scenarios} scenarios)")

    summary_lines.extend([
        f"Output Format: {args.format}",
        "",
        "Execution Timing:",
        "-" * 50,
        f"Model load: {format_time(timings['model_load'])}",
    ])

    # Add calculation timings with per-scenario metrics
    for calc_name in sorted(timings.keys()):
        if not calc_name.startswith(('gmxb_', 'glwb_')):
            continue

        calc_time = timings[calc_name]
        calc_label = calc_name.replace('_', ' ').upper()

        if isinstance(num_scenarios, int) and isinstance(num_points, int):
            per_scenario = calc_time / num_scenarios
            per_point = calc_time / num_points
            summary_lines.append(
                f"{calc_label}: {format_time(calc_time)} "
                f"({format_time(per_scenario)} per scenario, {format_time(per_point)} per model point)"
            )
        else:
            summary_lines.append(f"{calc_label}: {format_time(calc_time)}")

    if timings['filtering'] > 0.01:
        summary_lines.append(f"Filtering: {format_time(timings['filtering'])}")

    summary_lines.append(f"Saving: {format_time(timings['saving'])}")
    summary_lines.append(f"Total: {format_time(total_time)}")

    # Add performance metrics
    if isinstance(num_scenarios, int) and isinstance(num_points, int):
        summary_lines.extend([
            "",
            "Performance Metrics:",
            "-" * 50,
            f"Average per scenario: {format_time(calc_time / num_scenarios)}",
            f"Average per model point: {format_time(calc_time / num_points)}",
            f"Projections/second: {total_projections / calc_time:.1f}",
        ])

    # Add memory metrics
    final_mem = memory_snapshots['final']
    summary_lines.extend([
        "",
        "Memory Usage:",
        "-" * 50,
        f"Peak Python memory: {format_memory(final_mem['tracemalloc_peak'])}",
        f"Current Python memory: {format_memory(final_mem['tracemalloc_current'])}",
    ])

    if HAS_PSUTIL:
        summary_lines.extend([
            f"Process RSS (physical): {format_memory(final_mem['process_rss'])}",
            f"Process VMS (virtual): {format_memory(final_mem['process_vms'])}",
        ])

        # Add memory growth by stage
        if 'model_load' in memory_snapshots:
            start_rss = memory_snapshots['start'].get('process_rss', 0)
            load_rss = memory_snapshots['model_load'].get('process_rss', 0)
            final_rss = final_mem.get('process_rss', 0)

            summary_lines.extend([
                "",
                "Memory Growth:",
                f"  Model load: +{format_memory(load_rss - start_rss)}",
                f"  Calculations: +{format_memory(final_rss - load_rss)}",
                f"  Total growth: +{format_memory(final_rss - start_rss)}",
            ])
    else:
        summary_lines.append("(Install psutil for detailed process memory)")

    # Add output files
    summary_lines.extend([
        "",
        "Output Files:",
        "-" * 50,
    ])

    for filename, size in saved_files:
        summary_lines.append(f"{filename} ({format_bytes(size)})")

    summary_text = "\n".join(summary_lines)

    # Save summary
    summary_path = output_dir / "run_summary.txt"
    summary_path.write_text(summary_text)

    # Print summary
    print()
    print(summary_text)

    if args.verbose:
        print()
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Run complete!")

    # Stop memory tracking
    tracemalloc.stop()

    # Restore original scen_size in source file
    if original_scen_size_line is not None and scenarios_file.exists():
        content = scenarios_file.read_text()
        pattern = r'def scen_size\(\):\s*"""[^"]*"""\s*return \d+'
        new_content = re.sub(pattern, original_scen_size_line, content)
        scenarios_file.write_text(new_content)
        if args.verbose:
            print(f"Restored {scenarios_file.name}: scen_size() returns 100")

    return 0


if __name__ == "__main__":
    sys.exit(main())
