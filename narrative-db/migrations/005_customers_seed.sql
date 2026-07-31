-- Migration: 005_customers_seed.sql
-- Phase 22 follow-up: seed placeholder prospect/customer companies.
--
-- The customers table (004_additive_schemas.sql, Spec §11.2) was created with
-- zero rows, so external-world's generate_prospect_activity() (Phase 21/22)
-- could never fire — there were no relationship_status='prospect' rows to pick.
--
-- No seed roster was provided in spec for customers, same situation as the
-- employee roster (SPEC_CLARIFICATIONS #10). Building agent invents a
-- placeholder set of 6 prospect companies, clearly marked as swappable.
-- Sales/support reps are looked up by email from the existing 003_employees.sql
-- roster rather than hardcoded IDs, so this stays valid if that roster changes.

INSERT INTO customers
    (company_name, contact_name, contact_email, relationship_status,
     support_sla_hours, assigned_sales_rep_id, assigned_support_rep_id)
SELECT v.company_name, v.contact_name, v.contact_email, 'prospect',
       v.support_sla_hours,
       (SELECT id FROM employees WHERE email = v.sales_rep_email),
       (SELECT id FROM employees WHERE email = v.support_rep_email)
FROM (VALUES
    ('Northwind Traders',    'Priya Anand',      'priya.anand@northwindtraders.example',    24, 'frank.nakamura@fakecorp.internal', 'james.obi@fakecorp.internal'),
    ('Blue Harbor Logistics','Marcus Webb',      'marcus.webb@blueharborlogistics.example', 24, 'grace.patel@fakecorp.internal',    'karen.walsh@fakecorp.internal'),
    ('Cedarline Retail',     'Fiona Grant',      'fiona.grant@cedarlineretail.example',     48, 'henry.kim@fakecorp.internal',      'leo.ferreira@fakecorp.internal'),
    ('Summit Peak Analytics','Derek Osei',       'derek.osei@summitpeakanalytics.example',  24, 'ingrid.larsson@fakecorp.internal', 'james.obi@fakecorp.internal'),
    ('Rivergate Media',      'Sonia Alvarez',    'sonia.alvarez@rivergatemedia.example',    48, 'frank.nakamura@fakecorp.internal', 'karen.walsh@fakecorp.internal'),
    ('Ashford Manufacturing','Tom Whitfield',    'tom.whitfield@ashfordmanufacturing.example', 24, 'grace.patel@fakecorp.internal', 'leo.ferreira@fakecorp.internal')
) AS v(company_name, contact_name, contact_email, support_sla_hours, sales_rep_email, support_rep_email);
