# NetConfig Release 37 — NI-6 Enterprise Operations Delivery

Status: `IMPLEMENTED_TESTING_DEFERRED`.

This delivery productizes NI-6 Capacity, Failure Risk, Impact Simulation and Health analytics through `Manager.analytics`, scoped REST APIs and the Operations **Network Intelligence** console. It adds durable insight/job evidence, lifecycle state, filter/search, affected-object/evidence drill-down and explicit impact simulation. Analytics remains non-remediating; operators are routed only into the existing approval-gated Structured Changes, Desired State and Campaign workflows for action.

Qualification evidence is canonical in `VALIDATION_SUMMARY.md`. Source and clean-extraction full regression are **202 passed / 7 skipped / 0 failed**; selftest is **ALL PASS**; manifest/hygiene/artifact structure gates pass. Q-1 Ruff/mypy and live PostgreSQL/protocol/vendor/device/scale qualification remain deferred and are not PASS.

## Release 37 RPM install delivery

This delivery adds the canonical production installation path and package identity `2.0.0-37`. Use the AlmaLinux 10 RPM lifecycle documented in `INSTALL_RPM.md`, `opt/netconfig/INSTALL.md`, and `packaging/README.md`. The source bundle includes `packaging/install-rpm.sh`; a separate `netconfig-2.0.0-37-rpm-build-source.zip` is provided for transfer to an AlmaLinux 10 build host. No binary RPM is claimed from the Debian artifact runner because the target `rpmbuild`/Python 3.12 environment is absent.

Candidate artifact qualification for the RPM-install delivery: clean extraction and manifests PASS; full byte identity 175/175; extracted-tree regression 202 passed / 7 skipped / 0 failed; selftest ALL PASS. The binary `.rpm` is intentionally not fabricated on the Debian runner. Use the included RPM build-transfer bundle on AlmaLinux 10.
