"""Shared snapshot conditions for initial alerts, briefs and follow-through."""


def matching_rules(config, observations, comparisons):
    if len(observations) < config.minimum_venues:
        return []
    result = []
    if len(comparisons) >= config.minimum_venues:
        if all(row['oi_base_pct'] >= config.oi_change_pct for row in comparisons):
            if all(row['price_pct'] >= config.price_change_pct for row in comparisons):
                result.append('price_oi_up')
            elif all(row['price_pct'] <= -config.price_change_pct for row in comparisons):
                result.append('price_oi_down')
    funding = [obs.funding_bps_8h for obs in observations]
    if all(rate >= config.funding_extreme_bps_8h for rate in funding):
        result.append('positive_funding')
    elif all(rate <= -config.funding_extreme_bps_8h for rate in funding):
        result.append('negative_funding')
    if len(funding) >= 2 and max(funding) - min(funding) >= config.funding_spread_bps_8h:
        result.append('funding_divergence')
    return result
