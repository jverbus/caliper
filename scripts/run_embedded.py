from caliper_core import Profile, load_settings


def main() -> None:
    settings = load_settings(use_cache=False)
    if settings.profile is not Profile.EMBEDDED:
        raise SystemExit(
            "run_embedded expects CALIPER_PROFILE=embedded; "
            f"got {settings.profile.value!r}"
        )

    settings.ensure_runtime_dirs()
    print(f"running embedded scaffold with {settings.resolved_db_url()}")


if __name__ == "__main__":
    main()
