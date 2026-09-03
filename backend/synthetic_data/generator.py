import random
from datetime import datetime, timedelta, date
from typing import List, Tuple
from database.models import Customer, Invoice
import string

# Fixed seed for reproducibility
RANDOM_SEED = 42


class SyntheticDataGenerator:
    """Generate reproducible synthetic B2B customer and invoice data"""
    
    def __init__(self, seed: int = RANDOM_SEED):
        self.seed = seed
        random.seed(seed)
        self.industries = [
            "Manufacturing", "Retail", "Technology", "Healthcare",
            "Finance", "Construction", "Logistics", "Hospitality",
            "Education", "Media", "Real Estate", "Energy"
        ]
        self.delay_reasons = [
            "cash_flow",
            "mandate_pending",
            "technical_issue",
            "awaiting_approval",
            "budget_allocation",
            "partial_receipt",
            "invoice_discrepancy"
        ]
        self.customer_profiles = [
            {"name_prefix": "Reliable", "reliability": 0.85, "frequency": 0.1},
            {"name_prefix": "Slow", "reliability": 0.5, "frequency": 0.25},
            {"name_prefix": "StressPay", "reliability": 0.4, "frequency": 0.35},
            {"name_prefix": "NonResp", "reliability": 0.2, "frequency": 0.4},
            {"name_prefix": "Stable", "reliability": 0.8, "frequency": 0.15},
        ]
    
    def generate_customers(self, count: int = 20) -> List[Customer]:
        """Generate synthetic customers"""
        customers = []
        
        for i in range(count):
            profile = random.choice(self.customer_profiles)
            customer_id = f"CUST-{i+1:04d}"
            
            # Simulate customer history
            total_invoices = random.randint(1, 50)
            total_paid = random.uniform(0, 500000)
            
            customer = Customer(
                id=customer_id,
                name=f"{profile['name_prefix']} Corp #{i+1}",
                industry=random.choice(self.industries),
                reliability_score=profile['reliability'] + random.uniform(-0.1, 0.1),
                total_invoices=total_invoices,
                total_paid=total_paid,
            )
            customers.append(customer)
        
        return customers
    
    def generate_invoices(self, customers: List[Customer], count: int = 100) -> List[Tuple[Invoice, Customer]]:
        """Generate synthetic invoices for customers"""
        invoices = []
        today = date.today()
        
        for i in range(count):
            customer = random.choice(customers)
            invoice_id = f"INV-{i+1:06d}"
            
            # Distribute invoice amounts realistically
            amount = random.choice([
                random.uniform(5000, 25000),      # Small invoices
                random.uniform(25000, 100000),    # Medium invoices
                random.uniform(100000, 500000),   # Large invoices
            ])
            
            # Vary the number of days overdue
            days_overdue_distribution = random.random()
            if days_overdue_distribution < 0.2:  # 20% recently due
                days_overdue = random.randint(1, 15)
            elif days_overdue_distribution < 0.5:  # 30% moderately overdue
                days_overdue = random.randint(16, 60)
            else:  # 50% significantly overdue
                days_overdue = random.randint(61, 180)
            
            due_date = today - timedelta(days=days_overdue)
            invoice_date = due_date - timedelta(days=random.randint(30, 90))
            
            # Determine status
            status = "UNPAID"
            dispute_flag = False
            dispute_reason = None
            delay_reason = None
            
            # Some invoices already paid
            if random.random() < 0.15:  # 15% already paid
                status = "PAID"
            # Some invoices disputed
            elif random.random() < 0.08:  # 8% disputed
                status = "DISPUTED"
                dispute_flag = True
                dispute_reason = random.choice([
                    "Goods not received",
                    "Quality issue",
                    "Invoice duplicate",
                    "Price mismatch",
                    "Partial delivery",
                ])
            # Rest unpaid with delay reasons
            else:
                delay_reason = random.choice(self.delay_reasons)
            
            invoice = Invoice(
                id=invoice_id,
                customer_id=customer.id,
                amount=amount,
                invoice_date=invoice_date,
                due_date=due_date,
                status=status,
                dispute_flag=dispute_flag,
                dispute_reason=dispute_reason,
                delay_reason=delay_reason,
            )
            
            invoices.append((invoice, customer))
        
        return invoices
    
    def generate_batch(self, num_invoices: int = 100) -> Tuple[List[Customer], List[Tuple[Invoice, Customer]]]:
        """Generate a complete batch of customers and invoices"""
        # Calculate number of customers (roughly 1 customer per 5 invoices)
        num_customers = max(5, num_invoices // 5)
        
        customers = self.generate_customers(num_customers)
        invoices = self.generate_invoices(customers, num_invoices)
        
        return customers, invoices
