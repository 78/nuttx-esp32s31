# Board Profiles

The supported target is the **ESP32-S31-Function-CoreBoard-1**.

`defaults.conf` contains settings shared by all profiles. `production.conf`
contains the deployable port configuration without stress-test applications.
`validation.conf` extends production with the applications and diagnostics
required by the bounded hardware regression suite.

NuttX board defconfigs remain compatibility entry points. The root `build.sh`
and these profiles are the reproducible integration entry points.
