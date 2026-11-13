#!/usr/bin/env python3
"""Write mac_processes.h: the system processes of a logged-in macOS 14 Intel Mac."""
import sys
U = -1  # the session user
# (uid, path); order is start order, so pids ascend as after a boot.
SYSTEM = """
0 /usr/libexec/logd
0 /usr/libexec/smd
0 /usr/libexec/UserEventAgent
0 /System/Library/PrivateFrameworks/Uninstall.framework/Resources/uninstalld
0 /System/Library/Frameworks/CoreServices.framework/Versions/A/Frameworks/FSEvents.framework/Versions/A/Support/fseventsd
0 /System/Library/PrivateFrameworks/MediaRemote.framework/Support/mediaremoted
0 /usr/sbin/systemstats
0 /usr/libexec/configd
0 /System/Library/CoreServices/powerd.bundle/powerd
0 /usr/libexec/remoted
0 /usr/libexec/watchdogd
0 /System/Library/Frameworks/CoreServices.framework/Frameworks/Metadata.framework/Support/mds
0 /usr/libexec/kernelmanagerd
0 /usr/libexec/diskarbitrationd
0 /usr/sbin/syslogd
0 /usr/libexec/thermalmonitord
0 /usr/libexec/opendirectoryd
0 /System/Library/PrivateFrameworks/ApplePushService.framework/apsd
0 /System/Library/CoreServices/launchservicesd
24 /usr/libexec/timed
213 /usr/libexec/usbmuxd
0 /usr/sbin/securityd
261 /usr/libexec/nsurlsessiond
0 /usr/libexec/autofsd
242 /usr/libexec/dasd
0 /System/Library/CoreServices/logind
0 /System/Library/PrivateFrameworks/GenerationalStorage.framework/Versions/A/Support/revisiond
0 /usr/sbin/KernelEventAgent
0 /usr/sbin/bluetoothd
0 /usr/libexec/sandboxd
0 /usr/libexec/corebrightnessd
0 /usr/libexec/AirPlayXPCHelper
0 /usr/sbin/notifyd
241 /usr/sbin/distnoted
0 /usr/libexec/syspolicyd
0 /System/Library/CoreServices/loginwindow.app/Contents/MacOS/loginwindow
0 /System/Library/PrivateFrameworks/TCC.framework/Support/tccd
0 /System/Library/Frameworks/Security.framework/Versions/A/XPCServices/authd.xpc/Contents/MacOS/authd
0 /usr/sbin/cfprefsd
0 /usr/libexec/coreduetd
0 /usr/libexec/nehelper
0 /usr/libexec/runningboardd
205 /usr/libexec/locationd
0 /usr/libexec/sysmond
0 /usr/libexec/trustdFileHelper
263 /System/Library/PrivateFrameworks/CoreAnalytics.framework/Support/analyticsd
0 /usr/libexec/airportd
0 /usr/libexec/apfsd
0 /usr/libexec/PerfPowerServices
266 /usr/libexec/containermanagerd
0 /usr/libexec/lsd
0 /System/Library/CoreServices/sharedfilelistd
0 /usr/libexec/mobileassetd
0 /usr/libexec/secinitd
0 /usr/libexec/trustd
65 /usr/sbin/mDNSResponder
0 /usr/sbin/mDNSResponderHelper
0 /usr/libexec/symptomsd
0 /usr/libexec/keybagd
0 /usr/libexec/wifip2pd
0 /usr/libexec/usbd
0 /usr/libexec/endpointsecurityd
0 /usr/libexec/biometrickitd
0 /usr/libexec/coreservicesd
0 /System/Library/PrivateFrameworks/CoreSymbolication.framework/coresymbolicationd
0 /usr/libexec/PowerUIAgent
0 /usr/libexec/wifianalyticsd
0 /System/Library/PrivateFrameworks/WirelessDiagnostics.framework/Support/awdd
0 /usr/libexec/nesessionmanager
0 /usr/libexec/tzd
202 /usr/sbin/coreaudiod
0 /System/Library/Frameworks/CoreMediaIO.framework/Versions/A/Resources/com.apple.cmio.registerassistantservice
0 /System/Library/Frameworks/AudioToolbox.framework/AudioComponentRegistrar
88 /System/Library/PrivateFrameworks/SkyLight.framework/Resources/WindowServer
0 /usr/libexec/hidd
0 /System/Library/CoreServices/backupd.bundle/Contents/Resources/backupd-helper
0 /usr/sbin/systemsoundserverd
0 /usr/libexec/wifivelocityd
0 /usr/libexec/bootinstalld
0 /usr/libexec/securityd_service
0 /usr/libexec/searchpartyd
0 /usr/libexec/colorsync.displayservices
0 /usr/libexec/colorsyncd
0 /System/Library/CoreServices/SubmitDiagInfo
0 /usr/libexec/findmydeviced
0 /usr/libexec/dprivacyd
0 /usr/libexec/periodic-wrapper
0 /usr/libexec/aned
0 /usr/libexec/mmaintenanced
0 /usr/libexec/storagekitd
0 /System/Library/PrivateFrameworks/XprotectFramework.framework/Versions/A/XPCServices/XprotectService.xpc/Contents/MacOS/XprotectService
0 /Library/Apple/System/Library/CoreServices/XProtect.app/Contents/MacOS/XProtect
0 /usr/libexec/gamecontrollerd
0 /usr/libexec/audioclocksyncd
0 /usr/libexec/rtcreportingd
0 /usr/libexec/softwareupdated
0 /System/Library/PrivateFrameworks/SystemStatusServer.framework/Support/systemstatusd
0 /usr/libexec/mdmclient
0 /usr/libexec/triald_system
0 /usr/libexec/ioupsd
0 /usr/sbin/filecoordinationd
0 /usr/libexec/netbiosd
0 /usr/libexec/sysextd
0 /usr/libexec/nfcd
0 /usr/sbin/spindump
89 /System/Library/Frameworks/CoreServices.framework/Versions/A/Frameworks/Metadata.framework/Versions/A/Support/mds_stores
0 /System/Library/PrivateFrameworks/PackageKit.framework/Resources/system_installd
0 /System/Library/CoreServices/Software Update.app/Contents/Resources/suhelperd
0 /usr/libexec/applessdstatistics
0 /usr/libexec/ptpcamerad
0 /usr/libexec/smbd
0 /usr/libexec/misagent
"""
USER = """
/usr/sbin/cfprefsd
/usr/sbin/distnoted
/usr/libexec/UserEventAgent
/usr/libexec/lsd
/usr/libexec/trustd
/usr/libexec/secd
/usr/libexec/pboard
/usr/libexec/rapportd
/usr/libexec/nsurlsessiond
/usr/libexec/secinitd
/usr/libexec/containermanagerd
/usr/libexec/pkd
/usr/libexec/tccd
/usr/libexec/knowledge-agent
/usr/libexec/sharingd
/usr/libexec/dmd
/usr/libexec/routined
/usr/libexec/fmfd
/usr/libexec/keyboardservicesd
/usr/libexec/replayd
/usr/libexec/avconferenced
/usr/libexec/siriknowledged
/usr/libexec/proactived
/usr/libexec/triald
/usr/libexec/cloudd
/usr/libexec/bird
/usr/libexec/networkserviceproxy
/usr/libexec/remindd
/usr/libexec/findmylocateagent
/usr/libexec/ContinuityCaptureAgent
/usr/libexec/WiFiAgent
/usr/libexec/BackgroundTaskManagementAgent
/usr/libexec/universalaccessd
/usr/libexec/dataaccessd
/usr/libexec/swcd
/usr/libexec/biomesyncd
/usr/libexec/adprivacyd
/usr/libexec/studentd
/usr/libexec/duetexpertd
/usr/libexec/intelligenceplatformd
/usr/libexec/siriactionsd
/usr/libexec/mediaanalysisd
/usr/libexec/corespeechd
/usr/libexec/donotdisturbd
/usr/libexec/assistantd
/usr/libexec/ScreenTimeAgent
/usr/libexec/spotlightknowledged
/usr/libexec/financed
/usr/libexec/SidecarRelay
/usr/libexec/extensionkitservice
/usr/libexec/localizationswitcherd
/usr/libexec/feedbackd
/usr/libexec/nearbyd
/usr/libexec/seserviced
/usr/libexec/itunescloudd
/usr/libexec/amsaccountsd
/usr/libexec/amsengagementd
/usr/libexec/promotedcontentd
/usr/libexec/contextstored
/usr/libexec/coreduetd
/usr/libexec/accessoryupdaterd
/usr/libexec/webprivacyd
/usr/libexec/transparencyd
/usr/sbin/usernoted
/System/Library/CoreServices/Dock.app/Contents/MacOS/Dock
/System/Library/CoreServices/SystemUIServer.app/Contents/MacOS/SystemUIServer
/System/Library/CoreServices/Finder.app/Contents/MacOS/Finder
/System/Library/CoreServices/ControlCenter.app/Contents/MacOS/ControlCenter
/System/Library/CoreServices/NotificationCenter.app/Contents/MacOS/NotificationCenter
/System/Library/CoreServices/Spotlight.app/Contents/MacOS/Spotlight
/System/Library/CoreServices/WindowManager.app/Contents/MacOS/WindowManager
/System/Library/CoreServices/TextInputMenuAgent.app/Contents/MacOS/TextInputMenuAgent
/System/Library/CoreServices/AirPlayUIAgent.app/Contents/MacOS/AirPlayUIAgent
/System/Library/CoreServices/WiFiAgent.app/Contents/MacOS/WiFiAgent
/System/Library/CoreServices/CoreLocationAgent.app/Contents/MacOS/CoreLocationAgent
/System/Library/CoreServices/talagent
/System/Library/CoreServices/pbs
/System/Library/CoreServices/sharedfilelistd
/System/Library/CoreServices/iconservicesagent
/System/Library/CoreServices/diagnostics_agent
/System/Library/CoreServices/ReportCrash
/System/Library/CoreServices/Siri.app/Contents/MacOS/Siri
/System/Library/CoreServices/backgroundtaskmanagementd
/System/Library/CoreServices/cloudpaird
/System/Library/CoreServices/mapspushd
/System/Library/CoreServices/OSDUIHelper.app/Contents/MacOS/OSDUIHelper
/System/Library/CoreServices/UIKitSystem.app/Contents/MacOS/UIKitSystem
/System/Library/CoreServices/Dock.app/Contents/XPCServices/com.apple.dock.extra.xpc/Contents/MacOS/com.apple.dock.extra
/System/Library/CoreServices/Dock.app/Contents/XPCServices/DockHelper.xpc/Contents/MacOS/DockHelper
/System/Library/CoreServices/CoreServicesUIAgent.app/Contents/MacOS/CoreServicesUIAgent
/System/Library/Frameworks/CoreServices.framework/Frameworks/Metadata.framework/Versions/A/Support/mdworker_shared
/System/Library/Frameworks/CoreServices.framework/Frameworks/Metadata.framework/Versions/A/Support/mdbulkimport
/System/Library/Frameworks/CoreServices.framework/Frameworks/Metadata.framework/Versions/A/Support/corespotlightd
/System/Library/Frameworks/ApplicationServices.framework/Frameworks/ATS.framework/Support/fontd
/System/Library/Frameworks/ApplicationServices.framework/Versions/A/Frameworks/ATS.framework/Versions/A/Support/fontworker
/System/Library/Frameworks/ApplicationServices.framework/Frameworks/HIServices.framework/Versions/A/XPCServices/com.apple.hiservices-xpcservice.xpc/Contents/MacOS/com.apple.hiservices-xpcservice
/System/Library/Frameworks/AudioToolbox.framework/AudioComponentRegistrar
/System/Library/Frameworks/AudioToolbox.framework/XPCServices/com.apple.audio.SandboxHelper.xpc/Contents/MacOS/com.apple.audio.SandboxHelper
/System/Library/Frameworks/CoreTelephony.framework/Support/CommCenter
/System/Library/Frameworks/Accounts.framework/Versions/A/Support/accountsd
/System/Library/Frameworks/AddressBook.framework/Executables/ContactsAccountsService
/System/Library/Frameworks/AddressBook.framework/Helpers/AddressBookSourceSync.app/Contents/MacOS/AddressBookSourceSync
/System/Library/Frameworks/Contacts.framework/Support/contactsd
/System/Library/Frameworks/InputMethodKit.framework/Resources/imklaunchagent
/System/Library/Frameworks/LocalAuthentication.framework/Support/coreautha.bundle/Contents/MacOS/coreautha
/System/Library/Frameworks/CryptoTokenKit.framework/ctkd
/System/Library/Frameworks/CryptoTokenKit.framework/ctkahp.bundle/Contents/MacOS/ctkahp
/System/Library/Frameworks/Security.framework/Versions/A/Resources/CloudKeychainProxy.bundle/Contents/MacOS/CloudKeychainProxy
/System/Library/Frameworks/MediaAccessibility.framework/Versions/A/XPCServices/com.apple.accessibility.mediaaccessibilityd.xpc/Contents/MacOS/com.apple.accessibility.mediaaccessibilityd
/System/Library/Frameworks/QuickLookUI.framework/Versions/A/XPCServices/QuickLookUIService.xpc/Contents/MacOS/QuickLookUIService
/System/Library/Frameworks/VideoToolbox.framework/Versions/A/XPCServices/VTDecoderXPCService.xpc/Contents/MacOS/VTDecoderXPCService
/System/Library/Frameworks/Metal.framework/Versions/A/XPCServices/MTLCompilerService.xpc/Contents/MacOS/MTLCompilerService
/System/Library/Frameworks/AppKit.framework/Versions/C/XPCServices/ThemeWidgetControlViewService.xpc/Contents/MacOS/ThemeWidgetControlViewService
/System/Library/Frameworks/CoreServices.framework/Versions/A/Frameworks/LaunchServices.framework/Versions/A/Support/lsregister
/System/Library/Frameworks/ExtensionFoundation.framework/Versions/A/XPCServices/extensionkitservice.xpc/Contents/MacOS/extensionkitservice
/System/Library/PrivateFrameworks/CloudKitDaemon.framework/Support/cloudd
/System/Library/PrivateFrameworks/IDS.framework/identityservicesd.app/Contents/MacOS/identityservicesd
/System/Library/PrivateFrameworks/IMCore.framework/imagent.app/Contents/MacOS/imagent
/System/Library/PrivateFrameworks/CalendarDaemon.framework/Support/calaccessd
/System/Library/PrivateFrameworks/CalendarNotification.framework/Versions/A/XPCServices/CalNCService.xpc/Contents/MacOS/CalNCService
/System/Library/PrivateFrameworks/PhotoLibraryServices.framework/Versions/A/Support/photolibraryd
/System/Library/PrivateFrameworks/PhotoAnalysis.framework/Versions/A/Support/photoanalysisd
/System/Library/PrivateFrameworks/AssistantServices.framework/Versions/A/Support/assistant_service
/System/Library/PrivateFrameworks/AuthKit.framework/Versions/A/Support/akd
/System/Library/PrivateFrameworks/AppleMediaServices.framework/Resources/amsaccountsd
/System/Library/PrivateFrameworks/AppStoreDaemon.framework/Support/appstoreagent
/System/Library/PrivateFrameworks/CommerceKit.framework/Versions/A/Resources/commerce
/System/Library/PrivateFrameworks/CoreSuggestions.framework/Versions/A/Support/suggestd
/System/Library/PrivateFrameworks/CoreParsec.framework/parsecd
/System/Library/PrivateFrameworks/CoreFollowUp.framework/Versions/A/Support/followupd
/System/Library/PrivateFrameworks/CoreCDP.framework/Versions/A/Resources/cdpd
/System/Library/PrivateFrameworks/CoreSpeech.framework/corespeechd
/System/Library/PrivateFrameworks/ContextKit.framework/Versions/A/XPCServices/ContextService.xpc/Contents/MacOS/ContextService
/System/Library/PrivateFrameworks/DataAccess.framework/Support/dataaccessd
/System/Library/PrivateFrameworks/DoNotDisturbServer.framework/Support/donotdisturbd
/System/Library/PrivateFrameworks/FamilyCircle.framework/Versions/A/Resources/familycircled
/System/Library/PrivateFrameworks/GeoServices.framework/Versions/A/XPCServices/com.apple.geod.xpc/Contents/MacOS/com.apple.geod
/System/Library/PrivateFrameworks/HomeKitDaemon.framework/Support/homed
/System/Library/PrivateFrameworks/IMDPersistence.framework/XPCServices/IMDPersistenceAgent.xpc/Contents/MacOS/IMDPersistenceAgent
/System/Library/PrivateFrameworks/iCloudNotification.framework/iCloudNotificationAgent
/System/Library/PrivateFrameworks/iTunesCloud.framework/Support/itunescloudd
/System/Library/PrivateFrameworks/MediaRemote.framework/Support/mediaremoteagent
/System/Library/PrivateFrameworks/MessagesBlastDoorSupport.framework/Versions/A/XPCServices/MessagesBlastDoorService.xpc/Contents/MacOS/MessagesBlastDoorService
/System/Library/PrivateFrameworks/PassKitCore.framework/passd
/System/Library/PrivateFrameworks/SafariSafeBrowsing.framework/com.apple.Safari.SafeBrowsing.Service
/System/Library/PrivateFrameworks/ScreenTimeCore.framework/Versions/A/ScreenTimeAgent
/System/Library/PrivateFrameworks/SoftwareUpdate.framework/Resources/softwareupdate_notify_agent
/System/Library/PrivateFrameworks/StatusKit.framework/Versions/A/Support/StatusKitAgent
/System/Library/PrivateFrameworks/SyncedDefaults.framework/Support/syncdefaultsd
/System/Library/PrivateFrameworks/TelephonyUtilities.framework/callservicesd
/System/Library/PrivateFrameworks/TextInput.framework/Resources/keyboardservicesd
/System/Library/PrivateFrameworks/UsageTracking.framework/Versions/A/UsageTrackingAgent
/System/Library/PrivateFrameworks/UserActivity.framework/Agents/useractivityd
/System/Library/PrivateFrameworks/ViewBridge.framework/Versions/A/XPCServices/ViewBridgeAuxiliary.xpc/Contents/MacOS/ViewBridgeAuxiliary
/System/Library/PrivateFrameworks/WeatherDaemon.framework/weatherd
/System/Library/PrivateFrameworks/AMPLibrary.framework/Versions/A/Support/AMPLibraryAgent
/System/Library/PrivateFrameworks/AMPDevices.framework/Versions/A/Support/AMPDeviceDiscoveryAgent
/System/Library/PrivateFrameworks/CoreWLANKit.framework/Versions/A/XPCServices/WiFiProxy.xpc/Contents/MacOS/WiFiProxy
/System/Library/PrivateFrameworks/SkyLight.framework/Versions/A/Resources/AquaAppearanceHelper.app/Contents/MacOS/AquaAppearanceHelper
/System/Library/Input Methods/PressAndHold.app/Contents/PlugIns/PAH_Extension.appex/Contents/MacOS/PAH_Extension
/System/Library/ExtensionKit/Extensions/WallpaperIntentsExtension.appex/Contents/MacOS/WallpaperIntentsExtension
/System/Library/ExtensionKit/Extensions/WallpaperAerialsExtension.appex/Contents/MacOS/WallpaperAerialsExtension
/System/Library/CoreServices/WallpaperAgent.app/Contents/MacOS/WallpaperAgent
"""
rows = [(0, 0, 0, '/kernel_task')]
pid = 78
def step():
    global pid
    pid += 1 + (pid * 7 + 3) % 4
    return pid
login = None
for line in SYSTEM.strip().splitlines():
    uid, path = line.split(' ', 1)
    p = step()
    if path.endswith('/loginwindow'): login = p
    rows.append((p, 1, int(uid), path))
pid += 40
for path in USER.strip().splitlines():
    rows.append((step(), 1, U, path))
assert len({r[0] for r in rows}) == len(rows)
out = ['/* Generated by tools/build-mac-processes.py; do not edit. */',
       'static const struct darling_mac_process darling_mac_processes[] = {']
for p, pp, uid, path in rows:
    out.append('\t{ %d, %d, %d, "%s" },' % (p, pp, uid, path))
out.append('};')
open(sys.argv[1], 'w').write('\n'.join(out) + '\n')
print(len(rows), rows[-1][0])
