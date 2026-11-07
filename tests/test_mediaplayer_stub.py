"""Every MPRemoteCommandCenter command Electron 43 can send must exist.

The Riot Client's browser process aborted with "-[MPRemoteCommandCenter
changeRepeatModeCommand]: unrecognized selector" once its UI started media
playback. The command list below is every *Command selector in Electron
Framework 43.7.5's method names; target/action registration is used too.
"""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / 'tools/riot-electron43-frameworks/MediaPlayer.m').read_text()

ELECTRON_COMMANDS = (
    'bookmarkCommand', 'changePlaybackPositionCommand', 'changePlaybackRateCommand',
    'changeRepeatModeCommand', 'changeShuffleModeCommand', 'disableLanguageOptionCommand',
    'dislikeCommand', 'enableLanguageOptionCommand', 'likeCommand', 'nextTrackCommand',
    'pauseCommand', 'playCommand', 'previousTrackCommand', 'ratingCommand',
    'seekBackwardCommand', 'seekForwardCommand', 'skipBackwardCommand', 'skipForwardCommand',
    'stopCommand', 'togglePlayPauseCommand')


def implementation(cls):
    return SOURCE.split(f'@implementation {cls}\n', 1)[1].split('\n@end', 1)[0]


class MediaPlayerStub(unittest.TestCase):
    def test_command_center_answers_every_electron_command(self):
        center = implementation('MPRemoteCommandCenter')
        for selector in ELECTRON_COMMANDS:
            self.assertRegex(center, r'- \(MPRemoteCommand \*\)' + selector + r' \{', selector)

    def test_commands_accept_target_action_registration(self):
        command = implementation('MPRemoteCommand')
        for selector in (r'addTarget:\(id\)target action:\(SEL\)action',
                         r'addTargetWithHandler:\(id\)handler', r'removeTarget:\(id\)target',
                         r'setEnabled:\(BOOL\)enabled', r'isEnabled'):
            self.assertRegex(command, r'- \([^)]*\)' + selector, selector)


if __name__ == '__main__':
    unittest.main()
