from django.db import models

CURRENCY_MAX_LENGTH = 3
TIMEZONE_MAX_LENGTH = 50


class Currency(models.TextChoices):
    USD = "USD", "US Dollar"
    EUR = "EUR", "Euro"
    GBP = "GBP", "British Pound"
    JPY = "JPY", "Japanese Yen"
    AUD = "AUD", "Australian Dollar"
    CAD = "CAD", "Canadian Dollar"
    CHF = "CHF", "Swiss Franc"
    INR = "INR", "Indian Rupee"
    CNY = "CNY", "Chinese Yuan"
    BRL = "BRL", "Brazilian Real"


class Timezone(models.TextChoices):
    UTC = "UTC", "UTC"
    US_EASTERN = "America/New_York", "US Eastern"
    US_CENTRAL = "America/Chicago", "US Central"
    US_MOUNTAIN = "America/Denver", "US Mountain"
    US_PACIFIC = "America/Los_Angeles", "US Pacific"
    LONDON = "Europe/London", "London"
    PARIS = "Europe/Paris", "Paris / Central Europe"
    TOKYO = "Asia/Tokyo", "Tokyo"
    SHANGHAI = "Asia/Shanghai", "Shanghai"
    KOLKATA = "Asia/Kolkata", "India"
    SYDNEY = "Australia/Sydney", "Sydney"
    SAO_PAULO = "America/Sao_Paulo", "São Paulo"
    DUBAI = "Asia/Dubai", "Dubai"
    SINGAPORE = "Asia/Singapore", "Singapore"
    HONG_KONG = "Asia/Hong_Kong", "Hong Kong"
