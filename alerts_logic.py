# Logic for Alerts and AI Coach
from models import ProfileType, Income
import random

def check_growth_alerts(user, tax_info):
    """
    Prompt 8: Growth Watch.
    Alert if revenue hits 80% of 50M threshold.
    """
    alerts = []
    
    if user.profile_type != ProfileType.INDIVIDUAL:
        # Business Logic
        # Revenue is in tax_info.get('revenue') or user.turnover_estimate
        revenue = tax_info.get('revenue', 0)
        
        # Threshold: 50M (Small Company Exemption Limit)
        THRESHOLD = 50000000
        WARNING_LEVEL = 0.8 * THRESHOLD # 40M
        
        if revenue >= WARNING_LEVEL and revenue < THRESHOLD:
            alerts.append({
                "type": "warning",
                "title": "Approaching Tax Threshold",
                "message": f"Your revenue is ₦{revenue:,.0f}. You are reaching the ₦50M threshold where CIT becomes applicable (0% -> 25%). Prepare your accounts."
            })
        elif revenue >= THRESHOLD:
            alerts.append({
                "type": "info",
                "title": "CIT Applicable",
                "message": "You have crossed the ₦50M revenue mark. Companies Income Tax now applies."
            })
            
    return alerts

def get_ai_suggestions(user, tax_info, vat_savings):
    """
    Prompt 9: AI Financial Coach.
    Context-aware nudges.
    """
    suggestions = []
    
    # Generic Nudge
    suggestions.append(random.choice([
        "Did you save your receipts today?",
        "Tracking expenses daily reduces tax stress.",
        "Check your WHT credits - don't leave money on the table."
    ]))
    
    # 1. VAT Savings Nudge (Individual)
    if user.profile_type == ProfileType.INDIVIDUAL:
        if vat_savings == 0:
            suggestions.append("You haven't logged any Tuition or Book expenses. Did you know these are VAT exempt and we track savings?")
        else:
            suggestions.append(f"Great job! You've identified ₦{vat_savings:,.2f} in VAT savings on education.")
            
    # 2. Tax Efficiency Nudge
    effective_rate = 0
    gross = tax_info.get('gross_income', 0) if user.profile_type == ProfileType.INDIVIDUAL else tax_info.get('revenue', 0)
    tax = tax_info.get('total_tax', 0)
    
    if gross > 0:
        effective_rate = (tax / gross) * 100
        
    if effective_rate > 15 and user.profile_type == ProfileType.INDIVIDUAL:
        suggestions.append("Your effective tax rate is over 15%. Consider maximizing your Pension and NHF contributions to lower this.")
        
    # 3. Compliance Nudge (Business)
    if user.profile_type != ProfileType.INDIVIDUAL:
        suggestions.append("Ensure your VAT returns are filed by the 21st of this month to avoid penalties.")
        
    return suggestions
