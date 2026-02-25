"""
PrintTown Math Engine Tests
Run: pytest test_math_engine.py -v
"""
import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from services.math_engine import *


class TestOddsConversion:
    def test_american_to_implied_neg110(self):
        assert abs(american_to_implied_prob(-110) - 0.52381) < 0.001
    def test_american_to_implied_pos150(self):
        assert abs(american_to_implied_prob(150) - 0.40000) < 0.001
    def test_american_to_implied_neg200(self):
        assert abs(american_to_implied_prob(-200) - 0.66667) < 0.001
    def test_american_to_implied_pos100(self):
        assert abs(american_to_implied_prob(100) - 0.50000) < 0.001
    def test_zero_raises(self):
        with pytest.raises(ValueError): american_to_implied_prob(0)

    def test_prob_to_american_fav(self):
        assert implied_prob_to_american(0.60) == -150
    def test_prob_to_american_dog(self):
        assert implied_prob_to_american(0.40) == 150
    def test_prob_to_american_even(self):
        assert implied_prob_to_american(0.50) == 100
    def test_prob_invalid(self):
        with pytest.raises(ValueError): implied_prob_to_american(0.0)
        with pytest.raises(ValueError): implied_prob_to_american(1.0)

    def test_american_to_decimal(self):
        assert abs(american_to_decimal(-110) - 1.9091) < 0.001
        assert abs(american_to_decimal(150) - 2.50) < 0.001
        assert abs(american_to_decimal(100) - 2.00) < 0.001

    def test_decimal_to_american(self):
        assert decimal_to_american(2.50) == 150
        assert decimal_to_american(2.00) == 100

    def test_decimal_to_implied(self):
        assert abs(decimal_to_implied_prob(2.0) - 0.50) < 0.001
        assert abs(decimal_to_implied_prob(4.0) - 0.25) < 0.001

    def test_round_trips(self):
        for odds in [-300, -200, -150, -110, 100, 110, 150, 200, 300]:
            dec = american_to_decimal(odds)
            back = decimal_to_american(dec)
            assert abs(back - odds) <= 1, f"Failed for {odds}"


class TestVigRemoval:
    def test_standard_110(self):
        r = remove_vig_multiplicative([{'name':'A','american_odds':-110},{'name':'B','american_odds':-110}])
        assert abs(r[0]['devigged_prob'] - 0.50) < 0.001
        assert abs(r[1]['devigged_prob'] - 0.50) < 0.001

    def test_asymmetric(self):
        r = remove_vig_multiplicative([{'name':'F','american_odds':-150},{'name':'U','american_odds':130}])
        assert abs(r[0]['devigged_prob'] - 0.577) < 0.01
        assert abs(sum(o['devigged_prob'] for o in r) - 1.0) < 1e-10

    def test_three_way(self):
        r = remove_vig_multiplicative([{'name':'H','american_odds':-120},{'name':'D','american_odds':250},{'name':'A','american_odds':300}])
        assert abs(sum(o['devigged_prob'] for o in r) - 1.0) < 1e-10

    def test_overround(self):
        assert abs(calculate_overround([{'american_odds':-110},{'american_odds':-110}]) - 4.762) < 0.1


class TestConsensus:
    def test_sharp_weighted(self):
        c = build_consensus([{'sportsbook':'pinnacle','devigged_prob':0.55},{'sportsbook':'draftkings','devigged_prob':0.53}])
        assert abs(c - 0.5433) < 0.001

    def test_equal_weight(self):
        c = build_consensus([{'sportsbook':'draftkings','devigged_prob':0.55},{'sportsbook':'fanduel','devigged_prob':0.53}])
        assert abs(c - 0.54) < 0.001

    def test_market_normalized(self):
        m = build_consensus_for_market({
            'A': [{'sportsbook':'pinnacle','devigged_prob':0.55}],
            'B': [{'sportsbook':'pinnacle','devigged_prob':0.45}],
        })
        assert abs(sum(m.values()) - 1.0) < 0.001


class TestEV:
    def test_positive(self):
        assert abs(calculate_ev(0.55, 110) - 0.155) < 0.001
    def test_negative(self):
        assert calculate_ev(0.45, -110) < 0
    def test_breakeven(self):
        assert abs(calculate_ev(0.50, 100)) < 0.001
    def test_percent(self):
        assert abs(calculate_ev_percent(0.55, 110) - 15.5) < 0.1
    def test_is_positive(self):
        assert is_positive_ev(0.55, 110) is True
        assert is_positive_ev(0.45, -110) is False


class TestKelly:
    def test_full(self):
        assert abs(kelly_criterion(0.55, 110) - 0.1409) < 0.001
    def test_no_edge(self):
        assert kelly_criterion(0.50, -110) == 0.0
        assert kelly_criterion(0.40, -110) == 0.0
    def test_fractional(self):
        full = kelly_criterion(0.55, 110)
        assert abs(kelly_fractional(0.55, 110, 0.25) - full * 0.25) < 0.001
    def test_cap(self):
        assert kelly_fractional(0.80, 200, 0.25, 0.05) <= 0.05
    def test_bet_amount(self):
        assert abs(kelly_bet_amount(1000.0, 0.55, 110, 0.25) - 35.23) < 0.5


class TestCLV:
    def test_positive(self):
        assert abs(calculate_clv(0.53, 2.10) - 0.113) < 0.001
    def test_negative(self):
        assert calculate_clv(0.45, 2.10) < 0
    def test_from_american(self):
        assert abs(calculate_clv_from_american(0.53, 110) - 0.113) < 0.001


class TestParlay:
    def test_combined_odds(self):
        legs = [{'american_odds': 110}, {'american_odds': -110}]
        assert abs(parlay_combined_odds(legs) - 2.10 * american_to_decimal(-110)) < 0.01
    def test_combined_prob(self):
        assert abs(parlay_combined_prob([{'consensus_prob':0.55},{'consensus_prob':0.58}]) - 0.319) < 0.001
    def test_ev_positive(self):
        legs = [{'consensus_prob':0.55,'american_odds':110},{'consensus_prob':0.58,'american_odds':-110}]
        assert parlay_ev(legs) > 0
    def test_kelly_cap(self):
        legs = [{'consensus_prob':0.55,'american_odds':110},{'consensus_prob':0.58,'american_odds':-110}]
        assert parlay_kelly(legs, 0.25, 0.03) <= 0.03


class TestCorrelation:
    def test_same_game_market(self):
        assert leg_correlation({'game_id':'g1','sport_key':'nba','market_type':'h2h'},
                              {'game_id':'g1','sport_key':'nba','market_type':'h2h'}) == 1.0
    def test_same_game_diff(self):
        assert leg_correlation({'game_id':'g1','sport_key':'nba','market_type':'h2h'},
                              {'game_id':'g1','sport_key':'nba','market_type':'totals'}) == 0.7
    def test_same_sport(self):
        assert leg_correlation({'game_id':'g1','sport_key':'nba','market_type':'h2h'},
                              {'game_id':'g2','sport_key':'nba','market_type':'h2h'}) == 0.15
    def test_cross_sport(self):
        assert leg_correlation({'game_id':'g1','sport_key':'nba','market_type':'h2h'},
                              {'game_id':'g2','sport_key':'soccer_epl','market_type':'h2h'}) == 0.0


class TestSignalScore:
    def test_strong(self):
        s = calculate_signal_score(10.0, 0.12, 5, 'toward', 8.0)
        assert s >= 70
        assert signal_tier(s) == 'strong'
    def test_moderate(self):
        s = calculate_signal_score(5.0, 0.06, 3, 'toward', 5.0)
        assert 40 <= s < 70
        assert signal_tier(s) == 'moderate'
    def test_weak(self):
        s = calculate_signal_score(1.0, 0.01, 1, 'against', 0.0)
        assert s < 40
        assert signal_tier(s) == 'weak'


class TestPnL:
    def test_win(self):
        assert abs(calculate_pnl('win', 150, 100.0) - 150.0) < 0.01
    def test_loss(self):
        assert calculate_pnl('loss', 150, 100.0) == -100.0
    def test_push(self):
        assert calculate_pnl('push', 150, 100.0) == 0.0


class TestFullPipeline:
    def test_end_to_end(self):
        pin = remove_vig_multiplicative([dict(name='A',american_odds=-115),dict(name='B',american_odds=-105)])
        dk = remove_vig_multiplicative([dict(name='A',american_odds=-120),dict(name='B',american_odds=100)])
        tc = build_consensus([
            {'sportsbook':'pinnacle','devigged_prob':pin[0]['devigged_prob']},
            {'sportsbook':'draftkings','devigged_prob':dk[0]['devigged_prob']},
        ])
        assert 0.4 < tc < 0.7
        tb = 1.0 - tc
        ev_b = calculate_ev_percent(tb, 100)
        # Just verify it runs without error and returns a number
        assert isinstance(ev_b, float)

    def test_clv_pipeline(self):
        clv = calculate_clv(0.53, american_to_decimal(110))
        assert abs(clv - 0.113) < 0.001

if __name__ == '__main__':
    pytest.main([__file__, '-v'])
