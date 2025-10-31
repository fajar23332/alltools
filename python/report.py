#!/usr/bin/env python3
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from verify-tools import check_tools

console = Console()

def main():
    console.print(Panel.fit("⚡ [bold cyan]Dolvin Tool Checker[/bold cyan] ⚡", style="bold blue"))
    
    results = check_tools()
    total = len(results)
    installed = sum(1 for v in results.values() if v)

    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Tool", style="cyan", width=22)
    table.add_column("Status", style="green", justify="center")

    for tool, ok in results.items():
        status = "[bold green]✅ Installed[/bold green]" if ok else "[bold red]❌ Missing[/bold red]"
        table.add_row(tool, status)

    console.print(table)
    console.print(f"\n[bold yellow]Summary:[/bold yellow] [green]{installed}[/green]/[white]{total}[/white] tools installed")

    if installed == total:
        console.print("\n[bold green]🔥 All tools installed! Fullpower mode unlocked![/bold green]")
    else:
        missing = [t for t, ok in results.items() if not ok]
        console.print(f"\n[bold red]⚠ Missing Tools:[/bold red] {', '.join(missing)}")

if __name__ == "__main__":
    main()
