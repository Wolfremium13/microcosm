import json
import os
import unittest
from datetime import datetime
from itertools import chain
from unittest.mock import patch, MagicMock, mock_open

from source.display.board import Board
from source.foundation.catalogue import Namer, get_heathen_plan
from source.foundation.models import GameConfig, Faction, Heathen, Project, UnitPlan, Improvement, Unit, Blessing, \
    AIPlaystyle, AttackPlaystyle, ExpansionPlaystyle, VictoryType
from source.game_management.game_controller import GameController
from source.game_management.game_state import GameState
from source.saving.game_save_manager import save_game, SAVES_DIR, get_saves, load_game, save_stats, get_stats
from source.saving.save_encoder import SaveEncoder


class GameSaveManagerTest(unittest.TestCase):
    """
    The test class for game_save_manager.py.
    """
    TEST_CONFIG = GameConfig(4, Faction.NOCTURNE, True, True, True)

    @patch("source.game_management.game_controller.MusicPlayer")
    def setUp(self, _: MagicMock) -> None:
        """
        Initialise the test game state and controller objects. Note that we also mock out the MusicPlayer class that
        is used when constructing the GameController. This is because it will try to play music if not mocked.
        :param _: The unused MusicPlayer mock.
        """
        self.game_state = GameState()
        self.game_state.board = Board(self.TEST_CONFIG, Namer())
        self.game_state.gen_players(self.TEST_CONFIG)
        self.game_state.heathens = [Heathen(1, 2, (3, 4), get_heathen_plan(1))]
        self.game_controller = GameController()

    @patch("source.saving.game_save_manager.datetime")
    @patch("os.remove")
    @patch("os.listdir")
    @patch("source.saving.game_save_manager.open", new_callable=mock_open)
    def test_save_game(self,
                       open_mock: MagicMock,
                       listdir_mock: MagicMock,
                       remove_mock: MagicMock,
                       datetime_mock: MagicMock):
        """
        Ensure that when saving a game state, the correct autosave modifications occur, and the correct data is written.
        :param open_mock: The mock representation of the open() builtin, which is used to open the save file for
        writing.
        :param listdir_mock: The mock representation of os.listdir(), which is used to retrieve previous autosaves.
        :param remove_mock: The mock representation of os.remove(), which is used to delete old autosaves.
        :param datetime_mock: The mock representation of datetime.datetime, which is used to retrieve the current time.
        """
        test_saves = [
            "autosave-2023-01-07T13.35.00.json",
            "autosave-2023-01-07T13.30.00.json",
            "autosave-2023-01-07T13.40.00.json"
        ]
        test_time = datetime(2023, 1, 7, hour=13, minute=35, second=24)

        listdir_mock.return_value = test_saves
        datetime_mock.now.return_value = test_time

        # We expect the second save to be deleted because it is the oldest autosave.
        expected_deleted_autosave = os.path.join(SAVES_DIR, test_saves[1])
        # The save name should also be according to our test time.
        expected_save_name = os.path.join(SAVES_DIR, "autosave-2023-01-07T13.35.24.json")
        # Also determine the data we expect to be saved.
        expected_save_data = {
            "quads": list(chain.from_iterable(self.game_state.board.quads)),
            "players": self.game_state.players,
            "heathens": self.game_state.heathens,
            "turn": self.game_state.turn,
            "cfg": self.game_state.board.game_config,
            "night_status": {"until": self.game_state.until_night, "remaining": self.game_state.nighttime_left}
        }

        save_game(self.game_state, auto=True)
        # After saving, we expect the oldest autosave to have been deleted, a new save with the correct name to have
        # been created, and the correct data to have been written to said save.
        remove_mock.assert_called_with(expected_deleted_autosave)
        self.assertEqual(expected_save_name, open_mock.call_args[0][0])
        open_mock.return_value.write.assert_called_with(json.dumps(expected_save_data, cls=SaveEncoder))
        open_mock.return_value.close.assert_called()

    @patch("os.path.isfile", lambda *args: True)
    def test_save_stats(self):
        original_playtime = 100
        original_turns = 4
        original_defeats = 2
        added_playtime = 200
        added_victory = VictoryType.ELIMINATION
        added_faction = Faction.FUNDAMENTALISTS

        sample_stats = f"""
        {{
            "playtime": {original_playtime},
            "turns_played": {original_turns},
            "victories": {{}},
            "defeats": {original_defeats},
            "factions": {{}}
        }}
        """
        expected_new_stats = {
            "playtime": original_playtime + added_playtime,
            "turns_played": original_turns + 1,
            "victories": {
                added_victory: 1
            },
            "defeats": original_defeats + 1,
            "factions": {
                added_faction: 1
            }
        }

        with patch("source.saving.game_save_manager.open", mock_open(read_data=sample_stats)) as open_mock:
            save_stats(playtime=added_playtime,
                       increment_turn=True,
                       victory_to_add=added_victory,
                       increment_defeats=True,
                       faction_to_add=added_faction)
            open_mock.return_value.write.assert_called_with(json.dumps(expected_new_stats))

    @patch("os.path.isfile", lambda *args: True)
    def test_save_stats_existing_victory_faction(self):
        victory = VictoryType.ELIMINATION
        faction = Faction.FUNDAMENTALISTS

        sample_stats = f"""
        {{
            "playtime": 1.23,
            "turns_played": 1,
            "victories": {{
                "{victory}": 1
            }},
            "defeats": 0,
            "factions": {{
                "{faction}": 1
            }}
        }}
        """
        expected_new_stats = {
            "playtime": 1.23,
            "turns_played": 1,
            "victories": {
                victory: 2
            },
            "defeats": 0,
            "factions": {
                faction: 2
            }
        }

        with patch("source.saving.game_save_manager.open", mock_open(read_data=sample_stats)) as open_mock:
            save_stats(increment_turn=False, victory_to_add=victory, faction_to_add=faction)
            open_mock.return_value.write.assert_called_with(json.dumps(expected_new_stats))

    @patch("os.path.isfile", lambda *args: True)
    def test_get_stats(self):
        playtime = 1.23
        turns_played = 1
        victory = VictoryType.ELIMINATION
        victory_count = 2
        defeats = 3
        faction = Faction.FUNDAMENTALISTS
        faction_count = 3

        sample_stats = f"""
        {{
            "playtime": {playtime},
            "turns_played": {turns_played},
            "victories": {{
                "{victory}": {victory_count}
            }},
            "defeats": {defeats},
            "factions": {{
                "{faction}": {faction_count}
            }}
        }}
        """

        with patch("source.saving.game_save_manager.open", mock_open(read_data=sample_stats)):
            retrieved_stats = get_stats()
            self.assertEqual(playtime, retrieved_stats.playtime)
            self.assertEqual(turns_played, retrieved_stats.turns_played)
            self.assertIn(victory, retrieved_stats.victories)
            self.assertEqual(victory_count, retrieved_stats.victories[victory])
            self.assertEqual(defeats, retrieved_stats.defeats)
            self.assertIn(faction, retrieved_stats.factions)
            self.assertEqual(faction_count, retrieved_stats.factions[faction])

    def test_get_stats_no_file(self):
        retrieved_stats = get_stats()
        self.assertFalse(retrieved_stats.playtime)
        self.assertFalse(retrieved_stats.turns_played)
        self.assertFalse(retrieved_stats.victories)
        self.assertFalse(retrieved_stats.defeats)
        self.assertFalse(retrieved_stats.factions)

    @patch("source.saving.game_save_manager.SAVES_DIR", "source/tests/resources")
    @patch("source.game_management.game_controller.MusicPlayer")
    @patch("pyxel.mouse")
    def test_load_game(self, mouse_mock: MagicMock, _: MagicMock):
        """
        Ensure that a pre-defined save game is correctly loaded and the game objects instantiated as the correct
        classes.
        :param mouse_mock: The mock implementation of pyxel.mouse().
        :param _: The unused MusicPlayer mock.
        """

        # This test makes a number of assumptions, based on the data from the supplied resource/test-save.json file.
        # Note: this file needs to be updated whenever the game save format changes.
        #
        # Assumptions:
        # - There are 2 players, with the human player using The Nocturne as their faction.
        # - The human player has a populated quads_seen list, but the AI player doesn't, despite it being populated in
        #   the save file. This is because AI players have no use for them.
        # - The human player has no deployed units, but the AI player has 1.
        # - The AI player has a Warrior with increased power.
        # - The human player has 2 settlements and the AI player has 1.
        # - The human player's two settlements are constructing a project and a unit, while the AI's settlement is
        #   constructing an improvement.
        # - The human player's first settlement has four improvements, and their second has none. The AI player's
        #   settlement also has four improvements.
        # - Both of the human player's garrisons have a unit present, while the AI player's has none.
        # - Both players have ongoing blessings.
        # - The human player has completed a blessing, but the AI player has not.
        # - Naturally, the human player has no AI playstyle, but the AI player does have one.
        # - Since the game has only two players, both have the Elimination victory as imminent.
        # - There are four heathens in the game.
        # - The game is at turn 23, with 20 turns until nighttime.
        # - The game config has everything enabled.
        #
        # The subsequent test logic is separated by assumption.

        self.game_state = GameState()
        self.game_controller = GameController()

        self.game_controller.namer.reset = MagicMock()
        self.game_controller.menu.save_idx = 0
        self.game_controller.namer.remove_settlement_name = MagicMock()
        self.game_controller.music_player.stop_menu_music = MagicMock()
        self.game_controller.music_player.play_game_music = MagicMock()
        self.game_controller.last_turn_time = 0

        load_game(self.game_state, self.game_controller)

        human = self.game_state.players[0]
        ai = self.game_state.players[1]

        self.game_controller.namer.reset.assert_called()

        self.assertEqual(2, len(self.game_state.players))
        self.assertEqual(Faction.NOCTURNE, human.faction)

        self.assertTrue(human.quads_seen)
        self.assertFalse(ai.quads_seen)

        self.assertFalse(human.units)
        self.assertEqual(1, len(ai.units))
        self.assertTrue(isinstance(ai.units[0], Unit))
        self.assertTrue(isinstance(ai.units[0].plan, UnitPlan))

        self.assertEqual(105, ai.units[0].plan.power)

        self.assertEqual(2, len(human.settlements))
        self.assertEqual(1, len(ai.settlements))
        self.assertEqual(3, self.game_controller.namer.remove_settlement_name.call_count)

        self.assertTrue(isinstance(human.settlements[0].current_work.construction, Project))
        self.assertTrue(isinstance(human.settlements[1].current_work.construction, UnitPlan))
        self.assertTrue(isinstance(ai.settlements[0].current_work.construction, Improvement))

        self.assertEqual(4, len(human.settlements[0].improvements))
        self.assertFalse(human.settlements[1].improvements)
        self.assertEqual(4, len(ai.settlements[0].improvements))
        self.assertTrue(all(isinstance(imp, Improvement) for imp in human.settlements[0].improvements))
        self.assertTrue(all(isinstance(imp, Improvement) for imp in ai.settlements[0].improvements))

        self.assertEqual(1, len(human.settlements[0].garrison))
        self.assertEqual(1, len(human.settlements[1].garrison))
        self.assertFalse(ai.settlements[0].garrison)
        self.assertTrue(isinstance(human.settlements[0].garrison[0], Unit))
        self.assertTrue(isinstance(human.settlements[1].garrison[0], Unit))

        self.assertTrue(isinstance(human.ongoing_blessing.blessing, Blessing))
        self.assertTrue(isinstance(ai.ongoing_blessing.blessing, Blessing))

        self.assertEqual(1, len(human.blessings))
        self.assertFalse(ai.blessings)
        self.assertTrue(isinstance(human.blessings[0], Blessing))

        self.assertIsNone(human.ai_playstyle)
        self.assertTrue(isinstance(ai.ai_playstyle, AIPlaystyle))
        self.assertTrue(isinstance(ai.ai_playstyle.attacking, AttackPlaystyle))
        self.assertTrue(isinstance(ai.ai_playstyle.expansion, ExpansionPlaystyle))

        self.assertEqual(1, len(human.imminent_victories))
        self.assertEqual(1, len(ai.imminent_victories))

        self.assertEqual(4, len(self.game_state.heathens))
        self.assertTrue(all(isinstance(heathen, Heathen) for heathen in self.game_state.heathens))
        self.assertTrue(all(isinstance(heathen.plan, UnitPlan) for heathen in self.game_state.heathens))

        self.assertEqual(23, self.game_state.turn)
        self.assertEqual(20, self.game_state.until_night)
        self.assertFalse(self.game_state.nighttime_left)

        mouse_mock.assert_called_with(visible=True)
        self.assertTrue(self.game_controller.last_turn_time)
        self.assertTrue(self.game_state.game_started)
        self.assertFalse(self.game_state.on_menu)

        self.assertIsNotNone(self.game_state.board)
        self.assertTrue(self.game_state.board.game_config.biome_clustering)
        self.assertTrue(self.game_state.board.game_config.fog_of_war)
        self.assertTrue(self.game_state.board.game_config.climatic_effects)
        self.assertEqual(90, len(self.game_state.board.quads))
        self.assertEqual(self.game_state.board, self.game_controller.move_maker.board_ref)
        self.assertTupleEqual((self.game_state.players[0].settlements[0].location[0] - 12,
                               self.game_state.players[0].settlements[0].location[1] - 11), self.game_state.map_pos)
        self.assertEqual(self.game_state.players[0], self.game_state.board.overlay.current_player)
        self.game_controller.music_player.stop_menu_music.assert_called()
        self.game_controller.music_player.play_game_music.assert_called()

    @patch("source.saving.game_save_manager.SAVES_DIR", "source/tests/resources")
    def test_load_game_invalid(self):
        """
        Ensure that when an invalid save file is provided, the menu is updated to reflect that.
        """
        self.game_controller.menu.save_idx = 1

        self.assertFalse(self.game_controller.menu.load_failed)
        load_game(self.game_state, self.game_controller)
        self.assertTrue(self.game_controller.menu.load_failed)

    @patch("os.listdir")
    def test_get_saves(self, listdir_mock: MagicMock):
        """
        Ensure that when retrieving existing save files, the correct filters and ordering are applied before displaying
        them on the menu.
        :param listdir_mock: The mock representation of os.listdir(), which is used to retrieve file names from the
        saves directory.
        """
        # Set some fake data for the menu that we expect to be overwritten.
        self.game_controller.menu.saves = ["a", "b", "c"]
        self.game_controller.menu.save_idx = 999
        # In our first example, there are no existing save files.
        listdir_mock.return_value = []

        get_saves(self.game_controller)
        # As such, we expect the menu saves to be reset and the save index to be negative (which is used to select the
        # cancel button).
        self.assertFalse(self.game_controller.menu.saves)
        self.assertEqual(-1, self.game_controller.menu.save_idx)

        # Now return some mock files from the listdir() call.
        test_saves = [
            "README.md",
            ".secret_file",
            "save-2023-01-07T13.36.00.json",
            "autosave-2023-01-07T13.37.00.json"
        ]
        listdir_mock.return_value = test_saves
        # We expect the README and the dotfile to be filtered out, and the saves to have their names formatted.
        expected_saves = [
            "2023-01-07 13.37.00 (auto)",
            "2023-01-07 13.36.00"
        ]

        get_saves(self.game_controller)
        self.assertListEqual(expected_saves, self.game_controller.menu.saves)


if __name__ == '__main__':
    unittest.main()
