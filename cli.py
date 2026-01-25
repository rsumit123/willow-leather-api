#!/usr/bin/env python3
"""
CLI for testing Willow & Leather cricket simulation
"""
import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import track
from app.database import init_db, get_session
from app.models import Player, Team
from app.models.player import PlayerRole
from app.generators import PlayerGenerator
from app.engine import MatchEngine

console = Console()


@click.group()
def cli():
    """Willow & Leather - Cricket Management Simulation"""
    pass


@cli.command()
def init():
    """Initialize the database"""
    console.print("[yellow]Initializing database...[/yellow]")
    init_db()
    console.print("[green]Database initialized successfully![/green]")


@cli.command()
@click.option("--count", default=150, help="Number of players to generate")
def generate_players(count: int):
    """Generate fictional players for the auction pool"""
    console.print(f"[yellow]Generating {count} players...[/yellow]")

    init_db()
    players = PlayerGenerator.generate_player_pool(count)

    # Display sample players
    table = Table(title="Sample Generated Players")
    table.add_column("Name", style="cyan")
    table.add_column("Age")
    table.add_column("Nationality")
    table.add_column("Role", style="magenta")
    table.add_column("BAT", justify="right")
    table.add_column("BOWL", justify="right")
    table.add_column("OVR", justify="right", style="green")
    table.add_column("Base Price", justify="right")

    for player in players[:20]:  # Show first 20
        table.add_row(
            player.name,
            str(player.age),
            player.nationality,
            player.role.value,
            str(player.batting),
            str(player.bowling),
            str(player.overall_rating),
            f"₹{player.base_price:,}",
        )

    console.print(table)

    # Stats summary (calculate before saving to avoid detached instance issues)
    roles = {}
    nationalities = {}
    for p in players:
        roles[p.role.value] = roles.get(p.role.value, 0) + 1
        nationalities[p.nationality] = nationalities.get(p.nationality, 0) + 1

    # Save to database
    PlayerGenerator.save_players_to_db(players)
    console.print(f"[green]{len(players)} players saved to database![/green]")

    console.print("\n[bold]Role Distribution:[/bold]")
    for role, count in sorted(roles.items()):
        console.print(f"  {role}: {count}")

    console.print("\n[bold]Nationality Distribution:[/bold]")
    for nat, count in sorted(nationalities.items(), key=lambda x: -x[1]):
        console.print(f"  {nat}: {count}")


@cli.command()
def list_players():
    """List all players in the database"""
    session = get_session()
    players = session.query(Player).order_by(Player.overall_rating.desc()).all()

    if not players:
        console.print("[red]No players found. Run 'generate-players' first.[/red]")
        return

    table = Table(title=f"All Players ({len(players)} total)")
    table.add_column("ID")
    table.add_column("Name", style="cyan")
    table.add_column("Age")
    table.add_column("Nationality")
    table.add_column("Role", style="magenta")
    table.add_column("BAT", justify="right")
    table.add_column("BOWL", justify="right")
    table.add_column("OVR", justify="right", style="green")

    for player in players[:50]:  # Show top 50
        table.add_row(
            str(player.id),
            player.name,
            str(player.age),
            player.nationality,
            player.role.value,
            str(player.batting),
            str(player.bowling),
            str(player.overall_rating),
        )

    console.print(table)
    session.close()


@cli.command()
def simulate():
    """Simulate a test match between two random teams"""
    session = get_session()
    players = session.query(Player).all()

    if len(players) < 22:
        console.print("[red]Not enough players. Run 'generate-players' first.[/red]")
        return

    # Create two random teams of 11
    import random
    random.shuffle(players)

    # Team composition: 1 WK, 4 batsmen, 2 all-rounders, 4 bowlers
    def build_team(pool: list[Player]) -> list[Player]:
        team = []
        wks = [p for p in pool if p.role == PlayerRole.WICKET_KEEPER]
        bats = [p for p in pool if p.role == PlayerRole.BATSMAN]
        ars = [p for p in pool if p.role == PlayerRole.ALL_ROUNDER]
        bowls = [p for p in pool if p.role == PlayerRole.BOWLER]

        if wks:
            team.append(wks.pop(0))
        if len(bats) >= 4:
            team.extend(bats[:4])
            bats = bats[4:]
        if len(ars) >= 2:
            team.extend(ars[:2])
            ars = ars[2:]
        if len(bowls) >= 4:
            team.extend(bowls[:4])
            bowls = bowls[4:]

        # Fill remaining with any role
        remaining = wks + bats + ars + bowls
        while len(team) < 11 and remaining:
            team.append(remaining.pop(0))

        return team[:11]

    team1 = build_team(players[:75])
    team2 = build_team(players[75:])

    # Display teams
    console.print(Panel("[bold cyan]Team 1[/bold cyan]"))
    for p in team1:
        console.print(f"  {p.name} ({p.role.value}) - BAT: {p.batting}, BOWL: {p.bowling}")

    console.print(Panel("[bold magenta]Team 2[/bold magenta]"))
    for p in team2:
        console.print(f"  {p.name} ({p.role.value}) - BAT: {p.batting}, BOWL: {p.bowling}")

    console.print("\n[yellow]Simulating match...[/yellow]\n")

    # Simulate
    engine = MatchEngine()
    result = engine.simulate_match(team1, team2)

    # Display result
    console.print(Panel("[bold]Match Result[/bold]"))
    console.print(f"[cyan]Team 1:[/cyan] {result['innings1']['runs']}/{result['innings1']['wickets']} ({result['innings1']['overs']} overs) - RR: {result['innings1']['run_rate']}")
    console.print(f"[magenta]Team 2:[/magenta] {result['innings2']['runs']}/{result['innings2']['wickets']} ({result['innings2']['overs']} overs) - RR: {result['innings2']['run_rate']}")
    console.print(f"\n[bold green]Winner: {result['winner'].upper()}[/bold green]")
    console.print(f"[bold]Margin: {result['margin']}[/bold]")

    # Show scorecards
    console.print("\n[bold]First Innings Scorecard:[/bold]")
    _print_scorecard(engine.innings1)

    console.print("\n[bold]Second Innings Scorecard:[/bold]")
    _print_scorecard(engine.innings2)

    session.close()


def _print_scorecard(innings):
    """Print innings scorecard"""
    # Batting
    bat_table = Table(title="Batting")
    bat_table.add_column("Batter", style="cyan")
    bat_table.add_column("Dismissal")
    bat_table.add_column("R", justify="right")
    bat_table.add_column("B", justify="right")
    bat_table.add_column("4s", justify="right")
    bat_table.add_column("6s", justify="right")
    bat_table.add_column("SR", justify="right")

    for batter_id, bi in innings.batter_innings.items():
        dismissal = bi.dismissal if bi.is_out else "not out"
        bat_table.add_row(
            bi.player.name,
            dismissal,
            str(bi.runs),
            str(bi.balls),
            str(bi.fours),
            str(bi.sixes),
            f"{bi.strike_rate:.1f}",
        )

    console.print(bat_table)

    # Bowling
    bowl_table = Table(title="Bowling")
    bowl_table.add_column("Bowler", style="magenta")
    bowl_table.add_column("O", justify="right")
    bowl_table.add_column("R", justify="right")
    bowl_table.add_column("W", justify="right")
    bowl_table.add_column("Econ", justify="right")

    for bowler_id, spell in innings.bowler_spells.items():
        bowl_table.add_row(
            spell.player.name,
            spell.overs_display,
            str(spell.runs),
            str(spell.wickets),
            f"{spell.economy:.1f}",
        )

    console.print(bowl_table)


@cli.command()
@click.option("--matches", default=100, help="Number of matches to simulate")
def benchmark(matches: int):
    """Run multiple simulations to test realism"""
    session = get_session()
    players = session.query(Player).all()

    if len(players) < 22:
        console.print("[red]Not enough players. Run 'generate-players' first.[/red]")
        return

    import random
    from collections import defaultdict

    stats = defaultdict(list)

    console.print(f"[yellow]Running {matches} simulations...[/yellow]")

    for _ in track(range(matches), description="Simulating..."):
        random.shuffle(players)

        # Simple team building
        team1 = players[:11]
        team2 = players[11:22]

        engine = MatchEngine()
        result = engine.simulate_match(team1, team2)

        stats["first_innings_scores"].append(result["innings1"]["runs"])
        stats["second_innings_scores"].append(result["innings2"]["runs"])
        stats["first_innings_wickets"].append(result["innings1"]["wickets"])
        stats["second_innings_wickets"].append(result["innings2"]["wickets"])
        stats["chasing_wins"].append(1 if result["winner"] == "team2" else 0)

    # Display statistics
    console.print(Panel("[bold]Simulation Statistics[/bold]"))

    all_scores = stats["first_innings_scores"] + stats["second_innings_scores"]
    console.print(f"[cyan]Average Score:[/cyan] {sum(all_scores) / len(all_scores):.1f}")
    console.print(f"[cyan]Min Score:[/cyan] {min(all_scores)}")
    console.print(f"[cyan]Max Score:[/cyan] {max(all_scores)}")

    all_wickets = stats["first_innings_wickets"] + stats["second_innings_wickets"]
    console.print(f"[cyan]Average Wickets:[/cyan] {sum(all_wickets) / len(all_wickets):.1f}")

    chase_win_pct = sum(stats["chasing_wins"]) / len(stats["chasing_wins"]) * 100
    console.print(f"[cyan]Chasing Win %:[/cyan] {chase_win_pct:.1f}%")

    # Score distribution
    brackets = {"<120": 0, "120-149": 0, "150-179": 0, "180-199": 0, "200+": 0}
    for score in all_scores:
        if score < 120:
            brackets["<120"] += 1
        elif score < 150:
            brackets["120-149"] += 1
        elif score < 180:
            brackets["150-179"] += 1
        elif score < 200:
            brackets["180-199"] += 1
        else:
            brackets["200+"] += 1

    console.print("\n[bold]Score Distribution:[/bold]")
    for bracket, count in brackets.items():
        pct = count / len(all_scores) * 100
        bar = "█" * int(pct / 2)
        console.print(f"  {bracket:>8}: {bar} {pct:.1f}%")

    session.close()


if __name__ == "__main__":
    cli()
