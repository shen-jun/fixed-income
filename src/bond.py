"""
bond.py
Author: Jun Shen

Defines the Bond class, which represents a fixed-coupon Treasury security
(bill, note, or bond) and knows how to build its own coupon schedule,
cashflows, and accrued interest.

Day count convention implemented here is Actual/Actual (ICMA-style), which
is the convention used for U.S. Treasury notes and bonds. Treasury bills
are handled as the same object with coupon_rate = 0.0, which collapses
the cashflow schedule down to a single payment of face value at maturity.
"""

from datetime import date


class Bond:
    """
    Represents a single fixed income security.

    Parameters
    ----------
    bond_id : str
        Short identifier, e.g. "UST_10Y".
    face_value : float
        Par / redemption value, quoted per 100 (standard market convention).
    coupon_rate : float
        Annual coupon rate expressed as a decimal (0.0425 = 4.25%).
    coupon_frequency : int
        Number of coupon payments per year (2 for semiannual Treasuries).
    issue_date : datetime.date
        Date the security was issued.
    maturity_date : datetime.date
        Date the security redeems at par.
    day_count : str
        Day count convention label. Only "ACT/ACT" is implemented.
    """

    def __init__(self, bond_id, face_value, coupon_rate, coupon_frequency,
                 issue_date, maturity_date, day_count="ACT/ACT"):
        if maturity_date <= issue_date:
            raise ValueError("maturity_date must be after issue_date")
        if coupon_frequency <= 0:
            raise ValueError("coupon_frequency must be a positive integer")
        if day_count != "ACT/ACT":
            raise NotImplementedError(
                "Only ACT/ACT day count is currently supported."
            )

        self.bond_id = bond_id
        self.face_value = face_value
        self.coupon_rate = coupon_rate
        self.coupon_frequency = coupon_frequency
        self.issue_date = issue_date
        self.maturity_date = maturity_date
        self.day_count = day_count

        # cache the coupon schedule since it never changes for a given bond
        self._coupon_dates = None

    def coupon_payment(self):
        """Dollar amount of a single coupon payment, per 100 face value."""
        return self.face_value * self.coupon_rate / self.coupon_frequency

    def generate_coupon_dates(self):
        """
        Build the full coupon date schedule by walking backward from the
        maturity date in steps of (12 / coupon_frequency) months, stopping
        once we reach (or pass) the issue date. The schedule is returned in
        chronological order, oldest date first.

        This is done with plain month/year arithmetic rather than a date
        library helper, since we only need to add/subtract whole months.
        """
        if self._coupon_dates is not None:
            return self._coupon_dates

        months_step = 12 // self.coupon_frequency
        schedule = [self.maturity_date]
        current = self.maturity_date

        while True:
            year = current.year
            month = current.month - months_step
            while month <= 0:
                month += 12
                year -= 1
            day = current.day

            # handle short months (e.g. schedule day 31 landing in a
            # 30-day or February month) by clamping to the last valid day
            day = self._clamp_day(year, month, day)
            prev_date = date(year, month, day)

            if prev_date <= self.issue_date:
                break

            schedule.append(prev_date)
            current = prev_date

        schedule.reverse()
        self._coupon_dates = schedule
        return schedule

    @staticmethod
    def _clamp_day(year, month, day):
        """Return the largest valid day number <= day for the given month."""
        days_in_month = [31, 29 if Bond._is_leap(year) else 28, 31, 30, 31, 30,
                          31, 31, 30, 31, 30, 31]
        max_day = days_in_month[month - 1]
        return min(day, max_day)

    @staticmethod
    def _is_leap(year):
        return (year % 4 == 0 and year % 100 != 0) or (year % 400 == 0)

    def generate_cashflows(self, settlement_date):
        """
        Return the list of (date, amount) cashflows occurring strictly
        after settlement_date. The final cashflow includes redemption
        of face value in addition to the coupon.
        """
        coupon_dates = self.generate_coupon_dates()
        coupon_payment = self.coupon_payment()

        cashflows = []
        for d in coupon_dates:
            if d <= settlement_date:
                continue
            amount = coupon_payment
            if d == self.maturity_date:
                amount += self.face_value
            cashflows.append((d, amount))

        return cashflows

    def accrued_interest(self, settlement_date):
        """
        Accrued interest as of settlement_date, using the standard
        fraction-of-period approach:

            AI = coupon_payment * (days since last coupon / days in period)

        Returns 0.0 if settlement is on or after the last coupon date
        prior to maturity being the final payment itself (edge case at
        maturity), or if settlement is before the first coupon period
        begins (uses issue_date as the start of the first period).
        """
        coupon_dates = self.generate_coupon_dates()
        coupon_payment = self.coupon_payment()

        previous_coupon = self.issue_date
        next_coupon = None
        for d in coupon_dates:
            if d > settlement_date:
                next_coupon = d
                break
            previous_coupon = d

        if next_coupon is None:
            # settlement is on or after maturity -- nothing left to accrue
            return 0.0

        days_in_period = (next_coupon - previous_coupon).days
        days_accrued = (settlement_date - previous_coupon).days

        if days_in_period <= 0:
            return 0.0

        return coupon_payment * (days_accrued / days_in_period)

    def __repr__(self):
        return (f"Bond(id={self.bond_id}, coupon={self.coupon_rate:.4%}, "
                f"maturity={self.maturity_date.isoformat()})")
