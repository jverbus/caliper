from importlib import import_module


def test_scaffold_imports() -> None:
    modules = [
        "caliper_adapters",
        "caliper_core",
        "caliper_events",
        "caliper_ope",
        "caliper_policies",
        "caliper_reports",
        "caliper_reward",
        "caliper_sdk",
        "caliper_storage",
    ]
    for module in modules:
        import_module(module)
