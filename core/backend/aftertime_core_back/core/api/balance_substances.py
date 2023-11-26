import datetime

from core.models import balanceSubstances



def add(**kwargs):
    """

    :param kwargs:
        description: str
    :return:
    """
    return balanceSubstances.BalanceSubstances.add(**kwargs)


def substance_residues(**kwargs):
    return balanceSubstances.BalanceSubstances.objects.substance_residues(**kwargs)


def get_balances_by_substances(**kwargs):
    return balanceSubstances.BalanceSubstances.objects.get_balances_by_substances()


def get_all(**kwargs):
    return balanceSubstances.BalanceSubstances.objects.get_all()




