import unittest
from unittest.mock import patch, MagicMock

from source.display.board import Board
from source.foundation.catalogue import Namer, UNIT_PLANS, BLESSINGS, get_unlockable_improvements, get_improvement, \
    get_available_improvements, get_unit_plan, IMPROVEMENTS
from source.foundation.models import GameConfig, Faction, Unit, Player, Settlement, AIPlaystyle, AttackPlaystyle, \
    ExpansionPlaystyle, Blessing, Quad, Biome
from source.game_management.movemaker import search_for_relics_or_move, set_blessing, set_player_construction, \
    set_ai_construction


class MovemakerTest(unittest.TestCase):
    """
    The test class for movemaker.py.
    """
    TEST_CONFIG = GameConfig(2, Faction.NOCTURNE, True, True, True)
    TEST_BOARD = Board(TEST_CONFIG, Namer())
    TEST_UNIT = Unit(1, UNIT_PLANS[0].total_stamina, (3, 4), False, UNIT_PLANS[0])
    TEST_UNIT_2 = Unit(5, 6, (7, 8), False, UNIT_PLANS[0])
    TEST_UNIT_3 = Unit(9, 10, (11, 12), False, UNIT_PLANS[0])
    TEST_PLAYER = Player("TesterMan", Faction.NOCTURNE, 0, 0, [], [TEST_UNIT], [], set(), set(),
                         ai_playstyle=AIPlaystyle(AttackPlaystyle.NEUTRAL, ExpansionPlaystyle.NEUTRAL))
    TEST_SETTLEMENT = Settlement("Obstructionville", (0, 0), [], [], [])

    def setUp(self) -> None:
        """
        Generate the quads to use, locate a relic, and reset the test models.
        """
        self.TEST_BOARD.generate_quads(self.TEST_CONFIG.biome_clustering)
        self.QUADS = self.TEST_BOARD.quads
        # We need to find a relic quad before each test, because the quads are re-generated each time.
        self.relic_coords: (int, int) = -1, -1
        for i in range(2, 90):
            for j in range(2, 80):
                if self.QUADS[i][j].is_relic:
                    self.relic_coords = i, j
                    break
            if self.relic_coords[0] != -1:
                break
        # More than one relic can make the tests unreliable, so remove all others.
        for i in range(90):
            for j in range(80):
                if self.QUADS[i][j].is_relic and self.relic_coords != (i, j):
                    self.QUADS[i][j].is_relic = False
        self.TEST_UNIT.location = 3, 4
        self.TEST_UNIT.remaining_stamina = UNIT_PLANS[0].total_stamina
        self.TEST_UNIT.plan.heals = False
        # Position the other two units and settlement to be surrounding the relic, obstructing its access.
        self.TEST_UNIT_2.location = self.relic_coords[0] - 1, self.relic_coords[1]
        self.TEST_UNIT_3.location = self.relic_coords[0], self.relic_coords[1] + 1
        self.TEST_SETTLEMENT.location = self.relic_coords[0], self.relic_coords[1] - 1
        self.TEST_SETTLEMENT.current_work = None
        self.TEST_SETTLEMENT.quads = []
        self.TEST_SETTLEMENT.satisfaction = 50
        self.TEST_SETTLEMENT.improvements = []
        self.TEST_SETTLEMENT.level = 1
        self.TEST_SETTLEMENT.produced_settler = False
        self.TEST_PLAYER.units = [self.TEST_UNIT]
        self.TEST_PLAYER.blessings = []
        self.TEST_PLAYER.ongoing_blessing = None
        self.TEST_PLAYER.ai_playstyle = AIPlaystyle(AttackPlaystyle.NEUTRAL, ExpansionPlaystyle.NEUTRAL)
        self.TEST_PLAYER.settlements = [self.TEST_SETTLEMENT]
        self.TEST_PLAYER.faction = Faction.NOCTURNE

    def test_set_blessing_none_available(self):
        """
        Ensure that an AI player's blessing is not set if there are none available, i.e. they have undergone all of
        them.
        """
        # Give the player every blessing.
        self.TEST_PLAYER.blessings = BLESSINGS.values()

        self.assertIsNone(self.TEST_PLAYER.ongoing_blessing)
        set_blessing(self.TEST_PLAYER, (0, 0, 0, 0))
        self.assertIsNone(self.TEST_PLAYER.ongoing_blessing)

    def test_set_blessing_wealth(self):
        """
        Ensure that an AI player's blessing is set to the best possible one for wealth if that is what they are lacking.
        """
        self.assertIsNone(self.TEST_PLAYER.ongoing_blessing)
        set_blessing(self.TEST_PLAYER, (0, 1, 1, 1))
        # The blessing that yields the most wealth is Self-Locking Vaults, with 29.
        new_blessing: Blessing = self.TEST_PLAYER.ongoing_blessing.blessing
        self.assertEqual(BLESSINGS["sl_vau"], new_blessing)

    def test_set_blessing_harvest(self):
        """
        Ensure that an AI player's blessing is set to the best possible one for harvest if that is what they are
        lacking.
        """
        self.assertIsNone(self.TEST_PLAYER.ongoing_blessing)
        set_blessing(self.TEST_PLAYER, (1, 0, 1, 1))
        # The blessing that yields the most harvest is Self-Locking Vaults, with 25.
        new_blessing: Blessing = self.TEST_PLAYER.ongoing_blessing.blessing
        self.assertEqual(BLESSINGS["sl_vau"], new_blessing)

    def test_set_blessing_zeal(self):
        """
        Ensure that an AI player's blessing is set to the best possible one for zeal if that is what they are lacking.
        """
        self.assertIsNone(self.TEST_PLAYER.ongoing_blessing)
        set_blessing(self.TEST_PLAYER, (1, 1, 0, 1))
        # The blessing that yields the most zeal is Robotic Experiments, with 32.
        new_blessing: Blessing = self.TEST_PLAYER.ongoing_blessing.blessing
        self.assertEqual(BLESSINGS["rob_exp"], new_blessing)

    def test_set_blessing_fortune(self):
        """
        Ensure that an AI player's blessing is set to the best possible one for fortune if that is what they are
        lacking.
        """
        self.assertIsNone(self.TEST_PLAYER.ongoing_blessing)
        set_blessing(self.TEST_PLAYER, (1, 1, 1, 0))
        # The blessing that yields the most fortune is Divine Architecture, with 30.
        new_blessing: Blessing = self.TEST_PLAYER.ongoing_blessing.blessing
        self.assertEqual(BLESSINGS["div_arc"], new_blessing)

    def test_set_blessing_aggressive_unit(self):
        """
        Ensure than an aggressive AI player's blessing is set to the first one that unlocks a unit.
        """
        self.TEST_PLAYER.ai_playstyle.attacking = AttackPlaystyle.AGGRESSIVE

        self.assertIsNone(self.TEST_PLAYER.ongoing_blessing)
        set_blessing(self.TEST_PLAYER, (0, 0, 0, 0))
        # The first blessing that yields a unit is Beginner Spells.
        new_blessing: Blessing = self.TEST_PLAYER.ongoing_blessing.blessing
        self.assertEqual(BLESSINGS["beg_spl"], new_blessing)

    def test_set_blessing_aggressive_no_units(self):
        """
        Ensure than an aggressive AI player's blessing is set to the best possible one for wealth if that is what they
        are lacking and there are no remaining blessings that unlock units.
        """
        self.TEST_PLAYER.ai_playstyle.attacking = AttackPlaystyle.AGGRESSIVE
        # Technically this will result in duplicates in the list, but that doesn't matter for our purposes.
        self.TEST_PLAYER.blessings = [up.prereq for up in UNIT_PLANS if up.prereq is not None]

        self.assertIsNone(self.TEST_PLAYER.ongoing_blessing)
        set_blessing(self.TEST_PLAYER, (0, 1, 1, 1))
        # The blessing that yields the most wealth excluding those that yield units is Economic Movements, with 20.
        new_blessing: Blessing = self.TEST_PLAYER.ongoing_blessing.blessing
        self.assertEqual(BLESSINGS["eco_mov"], new_blessing)

    def test_set_blessing_defensive_strength(self):
        """
        Ensure than an defensive AI player's blessing is set to the first one that unlocks an improvement that yields
        strength.
        """
        self.TEST_PLAYER.ai_playstyle.attacking = AttackPlaystyle.DEFENSIVE

        self.assertIsNone(self.TEST_PLAYER.ongoing_blessing)
        set_blessing(self.TEST_PLAYER, (0, 0, 0, 0))
        # The first blessing that yields an improvement with strength is Rudimentary Explosives.
        new_blessing: Blessing = self.TEST_PLAYER.ongoing_blessing.blessing
        self.assertEqual(BLESSINGS["rud_exp"], new_blessing)

    def test_set_blessing_defensive_no_strength(self):
        """
        Ensure than a defensive AI player's blessing is set to the best possible one for harvest if that is what they
        are lacking and there are no remaining blessings that unlock improvements with strength.
        """
        self.TEST_PLAYER.ai_playstyle.attacking = AttackPlaystyle.DEFENSIVE
        # Give the player all the blessings that unlock improvements with strength.
        self.TEST_PLAYER.blessings = [bls for bls in BLESSINGS.values()
                                      if [imp for imp in get_unlockable_improvements(bls) if imp.effect.strength > 0]]

        self.assertIsNone(self.TEST_PLAYER.ongoing_blessing)
        set_blessing(self.TEST_PLAYER, (1, 0, 1, 1))
        # The blessing that yields the most harvest excluding those that yield strength is Metabolic Alterations, with
        # 15.
        new_blessing: Blessing = self.TEST_PLAYER.ongoing_blessing.blessing
        self.assertEqual(BLESSINGS["met_alt"], new_blessing)

    def test_set_player_construction_no_units(self):
        """
        Ensure that when a player has no deployed units nor any in the settlement's garrison, the first available unit
        is selected for construction.
        """
        self.TEST_PLAYER.units = []

        set_player_construction(self.TEST_PLAYER, self.TEST_SETTLEMENT, False)
        self.assertEqual(UNIT_PLANS[0], self.TEST_SETTLEMENT.current_work.construction)

    def test_set_player_construction_wealth(self):
        """
        Ensure that when a player's settlement is lacking wealth, the correct improvement is selected for construction.
        """
        # Harvest needs to be higher so that we are above the harvest boundary.
        self.TEST_SETTLEMENT.quads = [Quad(Biome.SEA, 0, 100, 1, 1)]
        self.TEST_PLAYER.blessings = list(BLESSINGS.values())
        # Remove a blessing to create a suitable test environment.
        self.TEST_PLAYER.blessings.remove(BLESSINGS["sl_vau"])

        set_player_construction(self.TEST_PLAYER, self.TEST_SETTLEMENT, False)
        # Technically, Planned Economy, which grants 20 wealth is the ideal improvement for this situation. However,
        # that improvement also decreases satisfaction by 2, meaning that the settlement's satisfaction would be lowered
        # to 48, which is not ideal. As such, Federal Museum is selected instead, as it has the next most wealth and
        # does not negatively impact satisfaction.
        self.assertEqual(get_improvement("Federal Museum"), self.TEST_SETTLEMENT.current_work.construction)

    def test_set_player_construction_harvest(self):
        """
        Ensure that when a player's settlement is lacking harvest, the correct improvement is selected for construction.
        """
        self.TEST_SETTLEMENT.quads = [Quad(Biome.DESERT, 100, 99, 100, 100)]
        self.TEST_PLAYER.blessings = list(BLESSINGS.values())
        # Remove a blessing to create a suitable test environment.
        self.TEST_PLAYER.blessings.remove(BLESSINGS["art_pht"])

        set_player_construction(self.TEST_PLAYER, self.TEST_SETTLEMENT, False)
        # Technically, Impenetrable Stores, which grants 25 harvest is the ideal improvement for this situation.
        # However, that improvement also decreases satisfaction by 5, meaning that the settlement's satisfaction would
        # be lowered to 45, which is not ideal. As such, Genetic Clinics is selected instead, as it has the next most
        # harvest and does not negatively impact satisfaction.
        self.assertEqual(get_improvement("Genetic Clinics"), self.TEST_SETTLEMENT.current_work.construction)

    def test_set_player_construction_zeal(self):
        """
        Ensure that when a player's settlement is lacking zeal, the correct improvement is selected for construction.
        """
        # Harvest needs to be higher so that we are above the harvest boundary.
        self.TEST_SETTLEMENT.quads = [Quad(Biome.SEA, 1, 100, 0, 1)]
        self.TEST_PLAYER.blessings = list(BLESSINGS.values())

        set_player_construction(self.TEST_PLAYER, self.TEST_SETTLEMENT, False)
        # Technically, Automated Production, which grants 30 zeal is the ideal improvement for this situation.
        # However, that improvement also decreases satisfaction by 10, meaning that the settlement's satisfaction would
        # be lowered to 40, which is not ideal. As such, Endless Mine is selected instead, as it has the next most
        # zeal and does not negatively impact satisfaction.
        self.assertEqual(get_improvement("Endless Mine"), self.TEST_SETTLEMENT.current_work.construction)

    @patch("source.game_management.movemaker.get_available_improvements")
    def test_set_player_construction_fortune(self, imps_mock: MagicMock):
        """
        Ensure that when a player's settlement is lacking fortune, the correct improvement is selected for construction.
        :param imps_mock: The mock implementation of the get_available_improvements() function.
        """
        # Harvest needs to be higher so that we are above the harvest boundary.
        self.TEST_SETTLEMENT.quads = [Quad(Biome.SEA, 1, 100, 1, 0)]
        self.TEST_PLAYER.blessings = [BLESSINGS["beg_spl"]]
        # We need to mock out the available improvements so as to achieve full coverage, reaching a block where the
        # improvement with the most fortune is updated. We do this by simply switching the first two improvements in the
        # list, as the eventual selection is normally the first in the list.
        test_imps = get_available_improvements(self.TEST_PLAYER, self.TEST_SETTLEMENT)
        test_imps[0], test_imps[1] = test_imps[1], test_imps[0]
        imps_mock.return_value = test_imps

        set_player_construction(self.TEST_PLAYER, self.TEST_SETTLEMENT, False)
        # Technically, Haunted Forest, which grants 8 fortune is the ideal improvement for this situation.
        # However, that improvement also decreases satisfaction by 5, meaning that the settlement's satisfaction would
        # be lowered to 45, which is not ideal. As such, Melting Pot is selected instead, as it has the next most
        # fortune and does not negatively impact satisfaction.
        self.assertEqual(get_improvement("Melting Pot"), self.TEST_SETTLEMENT.current_work.construction)

    def test_set_player_construction_unsatisfied_too_expensive(self):
        """
        Ensure that when a player's settlement is below 50 satisfaction, but there are no improvements that would
        increase it without taking too many turns, the ideal improvement is selected for construction instead.
        """
        # Harvest needs to be higher so that we are above the harvest boundary.
        self.TEST_SETTLEMENT.quads = [Quad(Biome.SEA, 1, 100, 0, 1)]
        self.TEST_SETTLEMENT.satisfaction = 49
        # Give the settlement all the improvements in the first 'tier' that grant satisfaction.
        self.TEST_SETTLEMENT.improvements = [
            get_improvement("Aqueduct"),
            get_improvement("Collectivised Farms"),
            get_improvement("City Market"),
            get_improvement("Melting Pot"),
            get_improvement("Insurmountable Walls")
        ]
        self.TEST_PLAYER.blessings = list(BLESSINGS.values())

        set_player_construction(self.TEST_PLAYER, self.TEST_SETTLEMENT, False)
        # Since any of the improvements in the second 'tier' take too many turns, we expect the ideal improvement to be
        # selected instead. In this case, the ideal improvement is Local Forge, since zeal is the lowest of the four.
        self.assertEqual(get_improvement("Local Forge"), self.TEST_SETTLEMENT.current_work.construction)

    def test_set_player_construction_unsatisfied(self):
        """
        Ensure that when a player's settlement is below 50 satisfaction, the improvement that would grant the most
        combined satisfaction and harvest upon completion without taking too many turns is selected for construction.
        """
        # Harvest needs to be higher so that we are above the harvest boundary.
        self.TEST_SETTLEMENT.quads = [Quad(Biome.SEA, 1, 100, 0, 1)]
        self.TEST_SETTLEMENT.satisfaction = 49
        self.TEST_PLAYER.blessings = list(BLESSINGS.values())

        set_player_construction(self.TEST_PLAYER, self.TEST_SETTLEMENT, False)
        # We expect the Aqueduct improvement to be selected, as it grants 2 harvest and 5 satisfaction, which is the
        # most combined in the first 'tier' of improvements.
        self.assertEqual(get_improvement("Aqueduct"), self.TEST_SETTLEMENT.current_work.construction)

    def test_set_player_construction_harvest_boundary(self):
        """
        Ensure that when a player's settlement is below the harvest boundary, the improvement that would grant the most
        harvest upon completion without taking too many turns is selected for construction.
        """
        # Harvest needs to be higher so that we are above the harvest boundary.
        self.TEST_SETTLEMENT.quads = [Quad(Biome.SEA, 100, 0, 100, 100)]
        self.TEST_PLAYER.blessings = list(BLESSINGS.values())

        set_player_construction(self.TEST_PLAYER, self.TEST_SETTLEMENT, False)
        # We expect the Collectivised Farms improvement to be selected, as it grants 10 harvest, which is the most in
        # the first 'tier' of improvements.
        self.assertEqual(get_improvement("Collectivised Farms"), self.TEST_SETTLEMENT.current_work.construction)

    def test_set_ai_construction_no_units(self):
        """
        Ensure that when an AI player has no deployed units nor any in the settlement's garrison, the first available
        unit is selected for construction.
        """
        self.TEST_PLAYER.units = []

        set_ai_construction(self.TEST_PLAYER, self.TEST_SETTLEMENT, False)
        self.assertEqual(UNIT_PLANS[0], self.TEST_SETTLEMENT.current_work.construction)

    def test_set_ai_construction_settler(self):
        """
        Ensure that AI players of different expansion playstyles produce settlers in their settlements at different
        levels.
        """
        # Expansionist AI players should produce a settler when their settlement reaches level 3.
        self.TEST_PLAYER.ai_playstyle.expansion = ExpansionPlaystyle.EXPANSIONIST
        self.TEST_SETTLEMENT.level = 2
        set_ai_construction(self.TEST_PLAYER, self.TEST_SETTLEMENT, False)
        # So, at level 2, we expect the construction to not be the settler unit (UNIT_PLANS[3]).
        self.assertNotEqual(UNIT_PLANS[3], self.TEST_SETTLEMENT.current_work.construction)

        self.TEST_SETTLEMENT.level = 3
        set_ai_construction(self.TEST_PLAYER, self.TEST_SETTLEMENT, False)
        # Now at level 3, we expect a settler to be constructed.
        self.assertEqual(UNIT_PLANS[3], self.TEST_SETTLEMENT.current_work.construction)

        # Neutral AI players should produce a settler when their settlement reaches level 5.
        self.TEST_PLAYER.ai_playstyle.expansion = ExpansionPlaystyle.NEUTRAL
        self.TEST_SETTLEMENT.level = 4
        set_ai_construction(self.TEST_PLAYER, self.TEST_SETTLEMENT, False)
        # At level 4, we expect the construction to not be the settler unit.
        self.assertNotEqual(UNIT_PLANS[3], self.TEST_SETTLEMENT.current_work.construction)

        self.TEST_SETTLEMENT.level = 5
        set_ai_construction(self.TEST_PLAYER, self.TEST_SETTLEMENT, False)
        # Now at level 5, we expect a settler to be constructed.
        self.assertEqual(UNIT_PLANS[3], self.TEST_SETTLEMENT.current_work.construction)

        # Hermit AI players should only produce a settler once their settlement reaches the maximum level of 10.
        self.TEST_PLAYER.ai_playstyle.expansion = ExpansionPlaystyle.HERMIT
        self.TEST_SETTLEMENT.level = 9
        set_ai_construction(self.TEST_PLAYER, self.TEST_SETTLEMENT, False)
        # At level 9, we expect the construction to not be the settler unit.
        self.assertNotEqual(UNIT_PLANS[3], self.TEST_SETTLEMENT.current_work.construction)

        self.TEST_SETTLEMENT.level = 10
        set_ai_construction(self.TEST_PLAYER, self.TEST_SETTLEMENT, False)
        # Now at level 10, we expect a settler to be constructed.
        self.assertEqual(UNIT_PLANS[3], self.TEST_SETTLEMENT.current_work.construction)

    def test_set_ai_construction_settler_concentrated(self):
        """
        Ensure that AI players of the Concentrated faction do not construct settlers at any level.
        """
        self.TEST_SETTLEMENT.level = 10
        self.TEST_PLAYER.faction = Faction.CONCENTRATED
        set_ai_construction(self.TEST_PLAYER, self.TEST_SETTLEMENT, False)
        # We expect the construction to not be the settler unit (UNIT_PLANS[3]).
        self.assertNotEqual(UNIT_PLANS[3], self.TEST_SETTLEMENT.current_work.construction)

    def test_set_ai_construction_settler_already_produced(self):
        """
        Ensure that AI player settlements that have already produced a settler cannot produce another one.
        """
        self.TEST_SETTLEMENT.level = 10
        self.TEST_SETTLEMENT.produced_settler = True
        set_ai_construction(self.TEST_PLAYER, self.TEST_SETTLEMENT, False)
        # We expect the construction to not be the settler unit (UNIT_PLANS[3]).
        self.assertNotEqual(UNIT_PLANS[3], self.TEST_SETTLEMENT.current_work.construction)

    def test_set_ai_construction_settler_dissatisfied(self):
        """
        Ensure that AI players with only dissatisfied settlements produce settlers as soon as their level increases.
        """
        self.TEST_SETTLEMENT.level = 2
        self.TEST_SETTLEMENT.satisfaction = 0
        set_ai_construction(self.TEST_PLAYER, self.TEST_SETTLEMENT, False)
        # We expect the construction to not be the settler unit (UNIT_PLANS[3]).
        self.assertEqual(UNIT_PLANS[3], self.TEST_SETTLEMENT.current_work.construction)

    def test_set_ai_construction_wealth(self):
        """
        Ensure that when an AI player's settlement is lacking wealth, the correct improvement is selected for
        construction.
        """
        # Harvest needs to be higher so that we are above the harvest boundary.
        self.TEST_SETTLEMENT.quads = [Quad(Biome.SEA, 0, 100, 1, 1)]
        self.TEST_PLAYER.blessings = list(BLESSINGS.values())
        # Remove a blessing to create a suitable test environment.
        self.TEST_PLAYER.blessings.remove(BLESSINGS["sl_vau"])

        set_ai_construction(self.TEST_PLAYER, self.TEST_SETTLEMENT, False)
        # Technically, Planned Economy, which grants 20 wealth is the ideal improvement for this situation. However,
        # that improvement also decreases satisfaction by 2, meaning that the settlement's satisfaction would be lowered
        # to 48, which is not ideal. As such, Federal Museum is selected instead, as it has the next most wealth and
        # does not negatively impact satisfaction.
        self.assertEqual(get_improvement("Federal Museum"), self.TEST_SETTLEMENT.current_work.construction)

    def test_set_ai_construction_harvest(self):
        """
        Ensure that when an AI player's settlement is lacking harvest, the correct improvement is selected for
        construction.
        """
        self.TEST_SETTLEMENT.quads = [Quad(Biome.DESERT, 100, 99, 100, 100)]
        self.TEST_PLAYER.blessings = list(BLESSINGS.values())
        # Remove a blessing to create a suitable test environment.
        self.TEST_PLAYER.blessings.remove(BLESSINGS["art_pht"])

        set_ai_construction(self.TEST_PLAYER, self.TEST_SETTLEMENT, False)
        # Technically, Impenetrable Stores, which grants 25 harvest is the ideal improvement for this situation.
        # However, that improvement also decreases satisfaction by 5, meaning that the settlement's satisfaction would
        # be lowered to 45, which is not ideal. As such, Genetic Clinics is selected instead, as it has the next most
        # harvest and does not negatively impact satisfaction.
        self.assertEqual(get_improvement("Genetic Clinics"), self.TEST_SETTLEMENT.current_work.construction)

    def test_set_ai_construction_zeal(self):
        """
        Ensure that when an AI player's settlement is lacking zeal, the correct improvement is selected for
        construction.
        """
        # Harvest needs to be higher so that we are above the harvest boundary.
        self.TEST_SETTLEMENT.quads = [Quad(Biome.SEA, 1, 100, 0, 1)]
        self.TEST_PLAYER.blessings = list(BLESSINGS.values())

        set_ai_construction(self.TEST_PLAYER, self.TEST_SETTLEMENT, False)
        # Technically, Automated Production, which grants 30 zeal is the ideal improvement for this situation.
        # However, that improvement also decreases satisfaction by 10, meaning that the settlement's satisfaction would
        # be lowered to 40, which is not ideal. As such, Endless Mine is selected instead, as it has the next most
        # zeal and does not negatively impact satisfaction.
        self.assertEqual(get_improvement("Endless Mine"), self.TEST_SETTLEMENT.current_work.construction)

    @patch("source.game_management.movemaker.get_available_improvements")
    def test_set_ai_construction_fortune(self, imps_mock: MagicMock):
        """
        Ensure that when an AI player's settlement is lacking fortune, the correct improvement is selected for
        construction.
        :param imps_mock: The mock implementation of the get_available_improvements() function.
        """
        # Harvest needs to be higher so that we are above the harvest boundary.
        self.TEST_SETTLEMENT.quads = [Quad(Biome.SEA, 1, 100, 1, 0)]
        self.TEST_PLAYER.blessings = [BLESSINGS["beg_spl"]]
        # We need to mock out the available improvements so as to achieve full coverage, reaching a block where the
        # improvement with the most fortune is updated. We do this by simply switching the first two improvements in the
        # list, as the eventual selection is normally the first in the list.
        test_imps = get_available_improvements(self.TEST_PLAYER, self.TEST_SETTLEMENT)
        test_imps[0], test_imps[1] = test_imps[1], test_imps[0]
        imps_mock.return_value = test_imps

        set_ai_construction(self.TEST_PLAYER, self.TEST_SETTLEMENT, False)
        # Technically, Haunted Forest, which grants 8 fortune is the ideal improvement for this situation.
        # However, that improvement also decreases satisfaction by 5, meaning that the settlement's satisfaction would
        # be lowered to 45, which is not ideal. As such, Melting Pot is selected instead, as it has the next most
        # fortune and does not negatively impact satisfaction.
        self.assertEqual(get_improvement("Melting Pot"), self.TEST_SETTLEMENT.current_work.construction)

    def test_set_ai_construction_unsatisfied_too_expensive(self):
        """
        Ensure that when an AI player's settlement is below 50 satisfaction, but there are no improvements that would
        increase it without taking too many turns, the ideal improvement is selected for construction instead.
        """
        # Harvest needs to be higher so that we are above the harvest boundary.
        self.TEST_SETTLEMENT.quads = [Quad(Biome.SEA, 1, 100, 0, 1)]
        self.TEST_SETTLEMENT.satisfaction = 49
        # Give the settlement all the improvements in the first 'tier' that grant satisfaction.
        self.TEST_SETTLEMENT.improvements = [
            get_improvement("Aqueduct"),
            get_improvement("Collectivised Farms"),
            get_improvement("City Market"),
            get_improvement("Melting Pot"),
            get_improvement("Insurmountable Walls")
        ]
        self.TEST_PLAYER.blessings = list(BLESSINGS.values())

        set_ai_construction(self.TEST_PLAYER, self.TEST_SETTLEMENT, False)
        # Since any of the improvements in the second 'tier' take too many turns, we expect the ideal improvement to be
        # selected instead. In this case, the ideal improvement is Local Forge, since zeal is the lowest of the four.
        self.assertEqual(get_improvement("Local Forge"), self.TEST_SETTLEMENT.current_work.construction)

    def test_set_ai_construction_unsatisfied(self):
        """
        Ensure that when an AI player's settlement is below 50 satisfaction, the improvement that would grant the most
        combined satisfaction and harvest upon completion without taking too many turns is selected for construction.
        """
        # Harvest needs to be higher so that we are above the harvest boundary.
        self.TEST_SETTLEMENT.quads = [Quad(Biome.SEA, 1, 100, 0, 1)]
        self.TEST_SETTLEMENT.satisfaction = 49
        self.TEST_PLAYER.blessings = list(BLESSINGS.values())

        set_ai_construction(self.TEST_PLAYER, self.TEST_SETTLEMENT, False)
        # We expect the Aqueduct improvement to be selected, as it grants 2 harvest and 5 satisfaction, which is the
        # most combined in the first 'tier' of improvements.
        self.assertEqual(get_improvement("Aqueduct"), self.TEST_SETTLEMENT.current_work.construction)

    def test_set_ai_construction_harvest_boundary(self):
        """
        Ensure that when an AI player's settlement is below the harvest boundary, the improvement that would grant the
        most harvest upon completion without taking too many turns is selected for construction.
        """
        # Harvest needs to be higher so that we are above the harvest boundary.
        self.TEST_SETTLEMENT.quads = [Quad(Biome.SEA, 100, 0, 100, 100)]
        self.TEST_PLAYER.blessings = list(BLESSINGS.values())

        set_ai_construction(self.TEST_PLAYER, self.TEST_SETTLEMENT, False)
        # We expect the Collectivised Farms improvement to be selected, as it grants 10 harvest, which is the most in
        # the first 'tier' of improvements.
        self.assertEqual(get_improvement("Collectivised Farms"), self.TEST_SETTLEMENT.current_work.construction)

    def test_set_ai_construction_aggressive_healer(self):
        """
        Ensure that when an aggressive AI player settlement does not have enough healers, the most proficient one is
        selected for construction.
        """
        self.TEST_PLAYER.ai_playstyle.attacking = AttackPlaystyle.AGGRESSIVE
        self.TEST_PLAYER.blessings = BLESSINGS.values()
        # Increase the settlement level so that the player does not have enough units.
        self.TEST_SETTLEMENT.level = 2
        # Harvest needs to be higher so that we are above the harvest boundary.
        self.TEST_SETTLEMENT.quads = [Quad(Biome.SEA, 1, 100, 0, 1)]

        set_ai_construction(self.TEST_PLAYER, self.TEST_SETTLEMENT, False)
        # We expect the Narcotician unit plan to be selected, as it has the greatest healing ability of all units.
        self.assertEqual(get_unit_plan("Narcotician"), self.TEST_SETTLEMENT.current_work.construction)

    def test_set_ai_construction_aggressive_unit(self):
        """
        Ensure that when an aggressive AI player settlement does not have enough units, the most powerful one is
        selected for construction.
        """
        self.TEST_PLAYER.ai_playstyle.attacking = AttackPlaystyle.AGGRESSIVE
        self.TEST_PLAYER.blessings = BLESSINGS.values()
        # Pretend that the player's unit is a healer so that an attacking unit will be selected instead.
        self.TEST_PLAYER.units[0].plan.heals = True
        # Increase the settlement level so that the player does not have enough units.
        self.TEST_SETTLEMENT.level = 2
        # Harvest needs to be higher so that we are above the harvest boundary.
        self.TEST_SETTLEMENT.quads = [Quad(Biome.SEA, 1, 100, 0, 1)]

        set_ai_construction(self.TEST_PLAYER, self.TEST_SETTLEMENT, False)
        # We expect the Haruspex unit plan to be selected, as it has the greatest power of all units.
        self.assertEqual(get_unit_plan("Haruspex"), self.TEST_SETTLEMENT.current_work.construction)

    def test_set_ai_construction_aggressive_enough_units(self):
        """
        Ensure that when an aggressive AI player settlement already has enough units, the ideal construction is selected
        instead.
        """
        self.TEST_PLAYER.ai_playstyle.attacking = AttackPlaystyle.AGGRESSIVE
        # Harvest needs to be higher so that we are above the harvest boundary.
        self.TEST_SETTLEMENT.quads = [Quad(Biome.SEA, 1, 100, 0, 1)]
        self.TEST_PLAYER.blessings = list(BLESSINGS.values())

        set_ai_construction(self.TEST_PLAYER, self.TEST_SETTLEMENT, False)
        # Normally, an aggressive AI would select a healer or a unit, but since they already have enough, their ideal
        # improvement is selected instead. In this case, it is Endless Mine.
        self.assertEqual(get_improvement("Endless Mine"), self.TEST_SETTLEMENT.current_work.construction)

    def test_set_ai_construction_defensive_healer(self):
        """
        Ensure that when a defensive AI player settlement does not have enough healers, the most proficient one is
        selected for construction.
        """
        self.TEST_PLAYER.ai_playstyle.attacking = AttackPlaystyle.DEFENSIVE
        self.TEST_PLAYER.blessings = BLESSINGS.values()
        # Increase the settlement level so that the player does not have enough units.
        self.TEST_SETTLEMENT.level = 3
        # Harvest needs to be higher so that we are above the harvest boundary.
        self.TEST_SETTLEMENT.quads = [Quad(Biome.SEA, 1, 100, 0, 1)]

        set_ai_construction(self.TEST_PLAYER, self.TEST_SETTLEMENT, False)
        # We expect the Narcotician unit plan to be selected, as it has the greatest healing ability of all units.
        self.assertEqual(get_unit_plan("Narcotician"), self.TEST_SETTLEMENT.current_work.construction)

    def test_set_ai_construction_defensive_unit(self):
        """
        Ensure that when a defensive AI player settlement does not have enough units, the one with the most health is
        selected for construction.
        """
        self.TEST_PLAYER.ai_playstyle.attacking = AttackPlaystyle.DEFENSIVE
        self.TEST_PLAYER.blessings = BLESSINGS.values()
        # Pretend that the player's unit is a healer so that an attacking unit will be selected instead.
        self.TEST_PLAYER.units[0].plan.heals = True
        # Increase the settlement level so that the player does not have enough units.
        self.TEST_SETTLEMENT.level = 3
        # Harvest needs to be higher so that we are above the harvest boundary.
        self.TEST_SETTLEMENT.quads = [Quad(Biome.SEA, 1, 100, 0, 1)]

        set_ai_construction(self.TEST_PLAYER, self.TEST_SETTLEMENT, False)
        # We expect the Fanatic unit plan to be selected, as it has the greatest health of all units.
        self.assertEqual(get_unit_plan("Fanatic"), self.TEST_SETTLEMENT.current_work.construction)

    def test_set_ai_construction_defensive_strength_improvement(self):
        """
        Ensure that when a defensive AI player settlement has enough units, but there are improvements available that
        increase settlement strength, said improvements are selected for construction.
        """
        self.TEST_PLAYER.ai_playstyle.attacking = AttackPlaystyle.DEFENSIVE
        self.TEST_PLAYER.blessings = BLESSINGS.values()
        # Harvest needs to be higher so that we are above the harvest boundary.
        self.TEST_SETTLEMENT.quads = [Quad(Biome.SEA, 1, 100, 0, 1)]

        set_ai_construction(self.TEST_PLAYER, self.TEST_SETTLEMENT, False)
        # Since Insurmountable Walls is the first improvement that increases strength, we expect it to be chosen.
        self.assertEqual(get_improvement("Insurmountable Walls"), self.TEST_SETTLEMENT.current_work.construction)

    def test_set_ai_construction_defensive_enough_units_no_strength_improvements(self):
        """
        Ensure that when a defensive AI player settlement already has enough units and there are no improvements
        available that increase strength, the ideal construction is selected instead.
        """
        self.TEST_PLAYER.ai_playstyle.attacking = AttackPlaystyle.DEFENSIVE
        # Harvest needs to be higher so that we are above the harvest boundary.
        self.TEST_SETTLEMENT.quads = [Quad(Biome.SEA, 100, 100, 0, 100)]
        # Give the settlement all the improvements that increase strength.
        self.TEST_SETTLEMENT.improvements = [imp for imp in IMPROVEMENTS if imp.effect.strength > 0]
        self.TEST_PLAYER.blessings = list(BLESSINGS.values())

        set_ai_construction(self.TEST_PLAYER, self.TEST_SETTLEMENT, False)
        # Normally, a defensive AI would select a healer, a unit, or an improvement that yields strength, but since they
        # already have enough units and there aren't any improvements of that kind available, their ideal improvement is
        # selected instead. In this case, it is Endless Mine.
        self.assertEqual(get_improvement("Endless Mine"), self.TEST_SETTLEMENT.current_work.construction)

    @patch("source.game_management.movemaker.investigate_relic", lambda *args: None)
    def test_search_for_relics_success_left(self):
        """
        Ensure that when a relic is within range and to the left of a unit, the unit investigates and removes it.
        """
        self.TEST_UNIT.location = self.relic_coords[0] - 2, self.relic_coords[1]

        self.assertTrue(self.TEST_UNIT.remaining_stamina)
        self.assertTrue(self.QUADS[self.relic_coords[0]][self.relic_coords[1]].is_relic)
        search_for_relics_or_move(self.TEST_UNIT, self.QUADS, self.TEST_PLAYER, [], [], self.TEST_CONFIG)

        # The unit should have moved directly to the left of the relic, and the quad should no longer have a relic.
        self.assertTupleEqual((self.relic_coords[0] - 1, self.relic_coords[1]), self.TEST_UNIT.location)
        self.assertFalse(self.TEST_UNIT.remaining_stamina)
        self.assertFalse(self.QUADS[self.relic_coords[0]][self.relic_coords[1]].is_relic)

    @patch("source.game_management.movemaker.investigate_relic", lambda *args: None)
    def test_search_for_relics_success_right(self):
        """
        Ensure that when a relic is within range and to the right of a unit, the unit investigates and removes it.
        """
        self.TEST_UNIT.location = self.relic_coords[0] + 2, self.relic_coords[1]

        self.assertTrue(self.TEST_UNIT.remaining_stamina)
        self.assertTrue(self.QUADS[self.relic_coords[0]][self.relic_coords[1]].is_relic)
        search_for_relics_or_move(self.TEST_UNIT, self.QUADS, self.TEST_PLAYER, [], [], self.TEST_CONFIG)

        # The unit should have moved directly to the right of the relic, and the quad should no longer have a relic.
        self.assertTupleEqual((self.relic_coords[0] + 1, self.relic_coords[1]), self.TEST_UNIT.location)
        self.assertFalse(self.TEST_UNIT.remaining_stamina)
        self.assertFalse(self.QUADS[self.relic_coords[0]][self.relic_coords[1]].is_relic)

    @patch("source.game_management.movemaker.investigate_relic", lambda *args: None)
    def test_search_for_relics_obstructed(self):
        """
        Ensure that when the three options for movement for a unit to a relic within range are obstructed, the unit just
        moves randomly instead. The three things that can obstruct a relic are player units, AI units, and settlements.
        In this test, we surround the relic with one of each.
        """
        self.TEST_PLAYER.units.append(self.TEST_UNIT_2)
        self.TEST_UNIT.location = self.relic_coords[0] - 2, self.relic_coords[1]

        self.assertTrue(self.TEST_UNIT.remaining_stamina)
        self.assertTrue(self.QUADS[self.relic_coords[0]][self.relic_coords[1]].is_relic)
        search_for_relics_or_move(self.TEST_UNIT, self.QUADS, self.TEST_PLAYER, [self.TEST_UNIT_3],
                                  [self.TEST_SETTLEMENT], self.TEST_CONFIG)

        # Normally, the unit would move directly to the left of the relic, but it can't move there, and as such, the
        # quad should still have a relic.
        self.assertNotEqual((self.relic_coords[0] - 1, self.relic_coords[1]), self.TEST_UNIT.location)
        self.assertFalse(self.TEST_UNIT.remaining_stamina)
        self.assertTrue(self.QUADS[self.relic_coords[0]][self.relic_coords[1]].is_relic)

    @patch("source.game_management.movemaker.investigate_relic", lambda *args: None)
    def test_search_for_relics_none_found(self):
        """
        Ensure that when there are no available relics, the unit moves randomly.
        """
        # Remove the last relic from the board.
        self.QUADS[self.relic_coords[0]][self.relic_coords[1]].is_relic = False

        self.assertTrue(self.TEST_UNIT.remaining_stamina)
        search_for_relics_or_move(self.TEST_UNIT, self.QUADS, self.TEST_PLAYER, [], [], self.TEST_CONFIG)
        # Make sure the unit exhausted its stamina.
        self.assertFalse(self.TEST_UNIT.remaining_stamina)

    """
    Make move cases to test / things to verify
    
    ---All in one test---
    Blessing is set
    Construction is set
    Construction is bought out in situations where it should be
    Settler is deployed
    Units are moved
    Units are sold
    
    ---Individual tests for deployment---
    Non-defensive AI auto-deploys garrisoned units
    Unit deployed when besieged
    Unit deployed when below max strength
    Unit deployed for defensive AI when not besieged and at max strength but garrison size of 4
    """


if __name__ == '__main__':
    unittest.main()
