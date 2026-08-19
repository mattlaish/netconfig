Name:           netconfig
Version:        2.0.0
Release:        16%{?dist}
Summary:        Network configuration and security operations console
License:        Proprietary
BuildArch:      noarch
Source0:        %{name}-%{version}.tar.gz

%global _python_bytecompile_extra 0

BuildRequires:  python3.12
BuildRequires:  systemd-rpm-macros
Requires:       /usr/bin/python3.12
Requires:       /usr/bin/ssh
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
* Wed Aug 19 2026 NetConfig Engineering <noreply@localhost> - 2.0.0-16
- Normalize Windows-prepared launcher and service text to LF
- Add packaged and installed launcher shebang regression checks

* Wed Aug 19 2026 NetConfig Engineering <noreply@localhost> - 2.0.0-15
- Reconstruct reproducible AlmaLinux 10 RPM and SRPM packaging
- Add bounded uploaded-MIB-driven vendor SNMP collection and visibility
- Reuse SNMPv3 localized keys and engine discovery to reduce poller CPU use
- Simplify pure-Application device settings
