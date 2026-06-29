import unittest

from pyobsim.errors import *
from pyobsim.book import Book
from pyobsim.side import Side
from pyobsim.participant import Participant
from pyobsim.order import Order

class TestBook(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.default_name = ""
        cls.default_participants = []

        cls.sample_name = "WOW"
        cls.sample_participants = [Participant(1, "John", 10000, 10),
                Participant(2, "Jane", 50000, 1200)]

    def test___init___normal(self):
        # assemble custom parameters
        params = {"PartialExecution": True,
                "AllowShorting": True,
                "AllowLending": False
                }
        
        actual_book = Book(self.sample_name, self.sample_participants, params)
       
        # check name and participants are correct
        self.assertEqual(actual_book.name, self.sample_name)
        self.assertEqual(actual_book.participants, self.sample_participants)
        
        # check parameters are correct
        for param_name, param_val in params.items():
            self.assertEqual(actual_book.get_param(param_name), param_val)

    def test___init___no_participants(self):
        actual_book = Book(self.sample_name, [])

        self.assertEqual(actual_book.name, self.sample_name)

    def test_add_normal(self):
        actual_book = Book(self.sample_name, self.sample_participants)

        test_order = Order(1, self.sample_participants[0], self.sample_name,
                "BID", 12.00, 150)

        actual_book.add(test_order)

        expected_bids = Side("BID")
        expected_bids.put(test_order)

        expected_asks = Side("ASK")

        self.assertEqual(actual_book.bids, expected_bids)
        self.assertEqual(actual_book.asks, expected_asks)
        self.assertEqual(actual_book.LTP, 0)

    def test_add_insufficient_funds(self):
        actual_book = Book(self.sample_name, self.sample_participants)

        test_order = Order(1, self.sample_participants[0], self.sample_name,
                "BID", 1000.00, 800)

        with self.assertRaises(InsufficientFundsError):
            actual_book.add(test_order)

    def test_add_no_cross(self):
        actual_book = Book(self.sample_name, self.sample_participants)

        test_orders = [Order(1, self.sample_participants[0], self.sample_name,
            "BID", 22.00, 3),
            Order(2, self.sample_participants[1], self.sample_name,
                "ASK", 100.00, 2)]

        # add order to book
        for order in test_orders:
            actual_book.add(order)

        expected_bids = Side("BID")
        expected_bids.put(test_orders[0])

        expected_asks = Side("ASK")
        expected_asks.put(test_orders[1])

        self.assertFalse(actual_book.crossed())
        self.assertEqual(actual_book.LTP, 0)
        self.assertEqual(actual_book.bids, expected_bids)
        self.assertEqual(actual_book.asks, expected_asks)

    def test_add_cross(self):
        actual_book = Book(self.sample_name, self.sample_participants)

        test_orders = [Order(1, self.sample_participants[0], self.sample_name,
            "BID", 22.00, 3),
            Order(2, self.sample_participants[1], self.sample_name,
                "ASK", 20.00, 3)]

        # add order to book
        for order in test_orders:
            actual_book.add(order)

        # expected Side objects
        expected_bids = Side("BID")
        expected_asks = Side("ASK")

        self.assertFalse(actual_book.crossed())
        self.assertEqual(actual_book.LTP, test_orders[0].price)
        self.assertEqual(actual_book.bids, expected_bids)
        self.assertEqual(actual_book.asks, expected_asks)

    def test_add_exact_match(self):
        actual_book = Book(self.sample_name, self.sample_participants)

        test_orders = [Order(1, self.sample_participants[0], self.sample_name,
            "BID", 22.00, 3),
            Order(2, self.sample_participants[1], self.sample_name,
                "ASK", 22.00, 3)]

        # add order to book
        for order in test_orders:
            actual_book.add(order)

        # expected Side objects
        expected_bids = Side("BID")
        expected_asks = Side("ASK")

        self.assertFalse(actual_book.crossed())
        self.assertEqual(actual_book.LTP, test_orders[0].price)
        self.assertEqual(actual_book.LTP, test_orders[1].price)
        self.assertEqual(actual_book.bids, expected_bids)
        self.assertEqual(actual_book.asks, expected_asks)

    def test_cancel_middle_of_level(self):
        # cancelling any non-head order at a price level must remove it
        # (regression for issue #2, bug 1)
        whale = Participant(3, "Whale", 1e12, 10**9)
        actual_book = Book(self.sample_name, [whale])

        for oid in (1, 2, 3):  # three bids, all at price 100
            actual_book.add(Order(oid, whale, self.sample_name, "BID", 100.0,
                10))

        actual_book.cancel(2)  # cancel the middle order

        self.assertEqual(actual_book.bids.volume, 20)
        self.assertEqual([o.id for o in actual_book.bids.get(100.0)], [1, 3])

    def test_cancel_last_of_level_prunes_price(self):
        # cancelling the final order at a level removes the price level itself
        whale = Participant(3, "Whale", 1e12, 10**9)
        actual_book = Book(self.sample_name, [whale])

        for oid in (1, 2):
            actual_book.add(Order(oid, whale, self.sample_name, "BID", 100.0,
                10))

        actual_book.cancel(1)  # cancel the head
        self.assertEqual([o.id for o in actual_book.bids.get(100.0)], [2])

        actual_book.cancel(2)  # cancel the remaining order, pruning the level
        self.assertEqual(actual_book.bids.prices, [])
        self.assertEqual(actual_book.bids.volume, 0)

    def test_cross_respects_price_priority(self):
        # a partial cross must consume the cheapest counter levels first and
        # leave the worse-priced level resting (regression for issue #2, bug 2)
        whale = Participant(3, "Whale", 1e12, 10**9)
        actual_book = Book(self.sample_name, [whale])

        for oid, px in [(1, 100), (2, 101), (3, 102)]:
            actual_book.add(Order(oid, whale, self.sample_name, "ASK",
                float(px), 10))

        # buy 20 @ 102 -> should take the 100 and 101 asks, leaving 102 resting
        actual_book.add(Order(4, whale, self.sample_name, "BID", 102.0, 20))

        self.assertEqual(actual_book.asks.best, 102.0)
        self.assertEqual(sorted(actual_book.asks.prices), [102.0])
        self.assertEqual(actual_book.LTP, 101.0)

    def test_full_sweep_executes_in_price_order(self):
        # a full sweep clears every level and finishes at the worst price
        whale = Participant(3, "Whale", 1e12, 10**9)
        actual_book = Book(self.sample_name, [whale])

        for oid, px in [(1, 100), (2, 101), (3, 102)]:
            actual_book.add(Order(oid, whale, self.sample_name, "ASK",
                float(px), 10))

        actual_book.add(Order(4, whale, self.sample_name, "BID", 102.0, 30))

        self.assertEqual(actual_book.asks.prices, [])
        self.assertEqual(actual_book.asks.volume, 0)
        self.assertEqual(actual_book.LTP, 102.0)

    def test_cancel_then_sweep_multi_order_levels(self):
        # both bugs jointly corrupt a sweep over multi-order levels after a
        # non-head cancellation; together the fixes conserve quantity exactly
        whale = Participant(3, "Whale", 1e12, 10**9)
        actual_book = Book(self.sample_name, [whale])

        # level 100: ids 1, 2 ; level 101: ids 3, 4
        for oid, px in [(1, 100), (2, 100), (3, 101), (4, 101)]:
            actual_book.add(Order(oid, whale, self.sample_name, "ASK",
                float(px), 10))

        actual_book.cancel(2)  # remove a non-head maker at 100
        self.assertEqual([o.id for o in actual_book.asks.get(100.0)], [1])

        # buy 30 takes id 1 (100), then ids 3 and 4 (101)
        actual_book.add(Order(5, whale, self.sample_name, "BID", 101.0, 30))

        self.assertEqual(actual_book.asks.prices, [])
        self.assertEqual(actual_book.asks.volume, 0)
        self.assertEqual(actual_book.LTP, 101.0)

