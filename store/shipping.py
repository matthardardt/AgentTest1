"""Shipping cost rules.

A simple, transparent flat-rate model:
  - Free shipping at/above ``free_shipping_threshold``.
  - Otherwise a flat ``shipping_flat_rate``.
  - An empty cart ships for $0.

Centralised here so the cart preview, the order/checkout total, and the Stripe
session all compute shipping identically.
"""

from config import get_settings

settings = get_settings()


def compute_shipping(subtotal: float) -> float:
    if subtotal <= 0:
        return 0.0
    if subtotal >= settings.free_shipping_threshold:
        return 0.0
    return round(settings.shipping_flat_rate, 2)
