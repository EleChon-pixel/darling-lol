# Qualification and release gate

Qualification separates reproducible source/build evidence from interactive
client observations. It does not log in, handle credentials, automate gameplay
or claim that an account is safe.

## Automated phases

Run the source and host checks into a private report directory:

```sh
python3 tools/qualify.py run --mode source --output build/qualification/source
python3 tools/qualify.py run --mode native --through preflight --output build/qualification/native
```

`--through build` also performs the full Darling build. In `nix` mode it runs
the same source/preflight/build commands inside the environment from which the
tool was invoked; use `nix develop` or the packaged FHS shell first. Reports and
logs are mode `0600` and contain the exact repository and patch-set identity.

## Interactive checkpoints

Installation and client phases are never started by the qualification tool.
After performing a documented step manually, record it with a small evidence
file such as a sanitized command transcript or `doctor.json`:

```sh
python3 tools/qualify.py record \
  --report build/qualification/native/report.json \
  --phase runtime_install --status pass \
  --evidence build/runtime-install-summary.txt
```

A manual pass requires evidence. The report stores only its basename, size and
SHA-256 digest, not the private path or contents. Never use account identifiers,
tokens, full client logs or credentials as evidence.

The checkpoints are `runtime_install`, `riot_bootstrap`, `client_install`,
`client_startup`, three independent client restarts, `client_update` and
`shutdown_cleanup`. Optional diagnostic checkpoints cover game startup,
rendering, and audio/input; they are observations, not an account-safety claim.

## Release gate

The policy in `qualification/release-policy.json` requires two complete runs on
independent hosts and distributions, both native and Nix installation modes,
and AMD plus either Intel or NVIDIA graphics. Every required phase must pass,
the reports must identify the same clean commit and patch set, and any recorded
failure blocks release:

```sh
python3 tools/qualify.py gate \
  build/qualification/host-a/report.json \
  build/qualification/host-b/report.json
```

Passing this gate establishes only the recorded compatibility behavior on those
machines. It does not establish Riot support, anti-cheat acceptance, account
safety, or future-client compatibility.
