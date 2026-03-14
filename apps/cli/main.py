import typer

app = typer.Typer(help="Caliper CLI (scaffold)")


@app.command()
def ping() -> None:
    """Basic scaffold sanity command."""
    print("pong")


if __name__ == "__main__":
    app()
