from django import template
from orders.money import rupees

register = template.Library()
register.filter("rupees", rupees)
