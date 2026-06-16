"""Simple keyword-based ticket categorization."""
import re


def auto_categorize(text: str) -> str:
    """
    Categorize ticket based on keywords.
    Returns: payment | order_stuck | refund | question | other
    """
    text_lower = text.lower()
    
    # Payment keywords
    if any(w in text_lower for w in ["оплат", "пополн", "баланс", "карт", "перевод", "деньги", "payment", "pay"]):
        return "payment"
    
    # Refund keywords
    if any(w in text_lower for w in ["возврат", "верн", "refund", "отмен"]):
        return "refund"
    
    # Order stuck keywords
    if any(w in text_lower for w in ["заказ", "не приш", "не получ", "застрял", "ожида", "order", "stuck", "pending"]):
        return "order_stuck"
    
    # Question keywords
    if any(w in text_lower for w in ["как", "почему", "что", "можно ли", "how", "why", "what", "can i", "?"]):
        return "question"
    
    return "other"
