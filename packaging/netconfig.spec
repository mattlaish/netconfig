Name:           netconfig
Version:        2.0.0
Release:        40%{?dist}
Summary:        Network configuration and security operations console
License:        Proprietary
BuildArch:      noarch
Source0:        %{name}-%{version}.tar.gz

%global _python_bytecompile_extra 0

BuildRequires:  python3.12
BuildRequires:  systemd-rpm-macros
Requires:       /usr/bin/python3.12
Requires:       /usr/bin/ssh
Requires:       /usr/bin/openssl
Requires(pre):  shadow-utils
%{?systemd_requires}

%description
NetConfig provides device inventory, encrypted credential storage, configuration
backup and diffing, approval workflows, compliance checks, SNMP monitoring,
NetFlow collection, application monitoring, and a web operations console.

%prep
%autosetup -n %{name}-%{version}

%build
PYTHONPYCACHEPREFIX="%{_tmppath}/%{name}-%{version}-pycache" \
    /usr/bin/python3.12 -m compileall -q opt/netconfig/netconfig opt/netconfig/selftest.py

%install
rm -rf "%{buildroot}"
install -d "%{buildroot}/opt/netconfig"
cp -a opt/netconfig/. "%{buildroot}/opt/netconfig/"
find "%{buildroot}/opt/netconfig" -type d -exec chmod 0755 {} +
find "%{buildroot}/opt/netconfig" -type f -exec chmod 0644 {} +
find "%{buildroot}/opt/netconfig" -type d -name __pycache__ -prune -exec rm -rf {} +
find "%{buildroot}/opt/netconfig" -type f -name '*.py[co]' -delete

# Defense in depth for sources copied from Windows: Linux shebangs require LF.
install -D -m 0755 /dev/null "%{buildroot}%{_bindir}/netconfig"
sed 's/\r$//' usr/bin/netconfig > "%{buildroot}%{_bindir}/netconfig"
chmod 0755 "%{buildroot}%{_bindir}/netconfig"
install -D -m 0644 usr/lib/systemd/system/netconfig-web.service \
    "%{buildroot}%{_unitdir}/netconfig-web.service"
install -D -m 0644 usr/lib/systemd/system/netconfig-backup.service \
    "%{buildroot}%{_unitdir}/netconfig-backup.service"
install -D -m 0644 usr/lib/systemd/system/netconfig-backup.timer \
    "%{buildroot}%{_unitdir}/netconfig-backup.timer"
install -D -m 0640 etc/default/netconfig "%{buildroot}%{_sysconfdir}/default/netconfig"
install -D -m 0644 etc/profile.d/netconfig.sh "%{buildroot}%{_sysconfdir}/profile.d/netconfig.sh"
install -d -m 0700 "%{buildroot}%{_localstatedir}/lib/netconfig"

%pre
getent group netconfig >/dev/null || groupadd -r netconfig
getent passwd netconfig >/dev/null || \
    useradd -r -g netconfig -d /var/lib/netconfig -s /sbin/nologin \
    -c "NetConfig service account" netconfig
exit 0

%post
%systemd_post netconfig-web.service netconfig-backup.timer

%preun
%systemd_preun netconfig-web.service netconfig-backup.timer

%postun
%systemd_postun_with_restart netconfig-web.service netconfig-backup.timer

%files
%dir /opt/netconfig
/opt/netconfig/netconfig
/opt/netconfig/selftest.py
/opt/netconfig/README.md
/opt/netconfig/INSTALL.md
/opt/netconfig/WEBGUI.md
/opt/netconfig/CREDENTIALS.md
%{_bindir}/netconfig
%{_unitdir}/netconfig-web.service
%{_unitdir}/netconfig-backup.service
%{_unitdir}/netconfig-backup.timer
%config(noreplace) %attr(0640,root,netconfig) %{_sysconfdir}/default/netconfig
%{_sysconfdir}/profile.d/netconfig.sh
%dir %attr(0700,netconfig,netconfig) %{_localstatedir}/lib/netconfig

%changelog
* Thu Sep 17 2026 OpenAI <noreply@openai.com> - 2.0.0-40
- Add NI-7 L3/VRF path and route-dependency intelligence
- Persist explicit route observations and fail closed on ambiguous/incomplete forwarding evidence
- Preserve analytics-only decision support; live Q-1 qualification remains deferred

* Wed Sep 16 2026 OpenAI <noreply@openai.com> - 2.0.0-39
- Q-1 Production Qualification Hardening: fix guarded installer release validation
- Pin Ruff/mypy qualification tools and GitHub Actions revisions for reproducible CI
- Add AlmaLinux 10 RPM build/static qualification CI job; keep installed-runtime gate explicit

* Wed Sep 16 2026 OpenAI <noreply@openai.com> - 2.0.0-38
- Git Reproducibility Hardening: commit required launchers/package helpers as Git 100755
- Pin Ruff CI gate and modernize Python 3.12 lint debt without broadening lint ignores
- Require fresh-clone source qualification before packaging

* Wed Sep 16 2026 OpenAI <noreply@openai.com> - 2.0.0-37
- Package Release 37 NI-6 Enterprise Operations & Qualification Hardening
- Add canonical AlmaLinux 10 RPM install/upgrade workflow and explicit first-admin bootstrap
- Preserve local-only web bind, noreplace configuration, runtime state, and deferred live qualification boundaries

* Sun Sep 13 2026 OpenAI <noreply@openai.com> - 2.0.0-34
- Add UI-1 Unified Automation & Operations Console for PH-4, NI-5, VM-1, NA-1, NA-2 and HA-1
- Preserve durable approval/snapshot verification for all network mutations; add telemetry edit and recovery evidence workflows
- Add UI-1 focused Web/RBAC/CSRF/CSP regressions and full source/artifact lineage evidence

* Sat Sep 12 2026 OpenAI <noreply@openai.com> - 2.0.0-33
- Add PH-4 structured configuration transactions with durable approval, verification, rollback and recovery evidence
- Add NI-5 telemetry, VM-1 model packs, NA-1 desired state, NA-2 fleet campaigns, and HA-1 control-plane recovery foundation
- Harden automation writes behind frozen change-request snapshots and preserve executable/source quality gates

* Sat Sep 12 2026 OpenAI <noreply@openai.com> - 2.0.0-32
- Qualification Q-1: production runtime/service-backed qualification harnesses
- Add controlled PostgreSQL core pg_dump/pg_restore workflow with checksum and destructive-restore guard
- Add runtime preflight, real PostgreSQL concurrency/leadership qualification tests, and hardened backup unit

* Sat Sep 12 2026 OpenAI <noreply@openai.com> - 2.0.0-31
- Platform Hardening PH-3: read-only NETCONF, RESTCONF and gNMI structured adapters
- Add per-device protocol profiles, explicit fail-closed fallback policy, CLI/API/Web surfaces
- Keep structured credentials vault-backed; gNMI uses a mode-0600 ephemeral config and secret-free argv

* Fri Sep 11 2026 OpenAI <noreply@openai.com> - 2.0.0-30
- Platform Hardening PH-2: optional PostgreSQL core backend with schema bootstrap and readiness
- Add advisory-lock scheduler leadership and SKIP LOCKED distributed task claiming
- Add protected pre-vault PostgreSQL service credential and SQLite-to-PostgreSQL migration tooling

* Fri Sep 11 2026 OpenAI <noreply@openai.com> - 2.0.0-29
- Platform Hardening PH-1: Web-console structural decomposition and strict nonce CSP

* Fri Sep 11 2026 NetConfig Engineering <noreply@localhost> - 2.0.0-28
- Add NI-4 operational alert acknowledge/resolve lifecycle and maintenance windows
- Add bounded SMTP notification retry/backoff plus durable scheduled operational reports
- Add NI-4 CLI, scoped REST API and Web Ops Alerts surfaces

* Fri Sep 11 2026 NetConfig Engineering <noreply@localhost> - 2.0.0-27
- Add NI-3 bounded SNMP v1/v2c Trap ingestion and normalized operational event stream
- Add targeted re-poll, event deduplication and NI-2 dependency-aware suppression
- Add events:read CLI/API/Web event visibility

* Fri Sep 11 2026 NetConfig Engineering <noreply@localhost> - 2.0.0-26
- Add NI-2 normalized LLDP/ENTITY-MIB chassis and IF-MIB interface identity
- Add fail-closed unique managed-neighbor resolution with ambiguity evidence
- Add bounded observed-L2 downstream impact via CLI, REST API and Web topology console

* Fri Sep 11 2026 NetConfig Engineering <noreply@localhost> - 2.0.0-25
- Add Network Intelligence NI-1 modern IP-neighbour and VLAN-aware Q-BRIDGE collection
- Add fail-closed IP/MAC/VLAN/switch/port endpoint correlation with staleness and ambiguity
- Add endpoint:read API scope plus CLI and Web endpoint inventory views

* Fri Sep 11 2026 NetConfig Engineering <noreply@localhost> - 2.0.0-24
- Close D.5 feature track with opt-in bounded diagnostic retention maintenance
- Preserve durable case metadata and exclude Incident-linked traces from generic pruning

* Fri Sep 11 2026 NetConfig Engineering <noreply@localhost> - 2.0.0-23
- Add D.5 Phase 4F Incident Web Console over existing Incident/evidence services

* Fri Sep 11 2026 NetConfig Engineering <noreply@localhost> - 2.0.0-22
- Add D.5 Phase 4E bounded secret-safe protocol trace capture for CLI/OpenSSH and SNMP

* Fri Sep 11 2026 NetConfig Engineering <noreply@localhost> - 2.0.0-21
- Add D.5 Phase 4D Ed25519 manifest signing and independent fingerprint trust verification
- Keep private signing keys external via systemd credentials or an explicit protected file path
- Add signed diagnostic/support-case verification through CLI and scoped API endpoints

* Fri Sep 11 2026 NetConfig Engineering <noreply@localhost> - 2.0.0-20
- Add D.5 Phase 4C bounded support-case export with reference-only incident/timeline indexes
- Add managed case-export storage, incident:export API scope, CLI/API create/list/download and SHA-256 manifests

* Fri Sep 11 2026 NetConfig Engineering <noreply@localhost> - 2.0.0-19
- Add D.5 Phase 4B reference-only incident evidence links and unified timeline
- Add immutable drift archive references plus incident timeline CLI/API operations

* Fri Sep 11 2026 NetConfig Engineering <noreply@localhost> - 2.0.0-18
- Add D.5 Phase 4A incident model, lifecycle CLI/API and diagnostic bundle association
- Repair debug download/admin bearer scope registration

* Wed Aug 19 2026 NetConfig Engineering <noreply@localhost> - 2.0.0-16
- Normalize Windows-prepared launcher and service text to LF
- Add packaged and installed launcher shebang regression checks

* Wed Aug 19 2026 NetConfig Engineering <noreply@localhost> - 2.0.0-15
- Reconstruct reproducible AlmaLinux 10 RPM and SRPM packaging
- Add bounded uploaded-MIB-driven vendor SNMP collection and visibility
- Reuse SNMPv3 localized keys and engine discovery to reduce poller CPU use
- Simplify pure-Application device settings

* Wed Aug 26 2026 NetConfig Engineering <noreply@localhost> - 2.0.0-17
- Add dashboard device grouping and search
- Add 24-hour interface history graph
- Add optional PostgreSQL interface-history storage and database settings
- Include the latest GitHub and Claude branch updates