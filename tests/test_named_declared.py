"""Named declared members vs verify_declared. Exact is not auto-clear."""

from residual_zero.features import FeatureFlags, load_features


def test_named_declared_flag_on_in_product_yaml():
    flags = load_features()
    assert flags.f58_named_declared_members is True
    assert FeatureFlags.all_off().f58_named_declared_members is False
    assert flags.f59_settlement_declared_ops is True
    assert FeatureFlags.all_off().f59_settlement_declared_ops is False
    assert flags.f60_reconstruct_missing_rate_ids is True
    assert FeatureFlags.all_off().f60_reconstruct_missing_rate_ids is False
