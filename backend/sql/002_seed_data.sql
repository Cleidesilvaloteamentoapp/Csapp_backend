-- =============================================================================
-- CSApp Backend – Dados de teste (Seed)
-- Execute no SQL Editor do Supabase APÓS 000_create_tables.sql e 001_rls_policies.sql
-- =============================================================================

-- IDs fixos para referência cruzada (todos hex válido)
-- Admin Supabase:    db79fbda-8ecd-49ae-b590-0dea1a5f26ad
-- Cliente Supabase:  00df9257-e938-4105-86a1-8bfb98d2ab67
-- Company:           a1b2c3d4-0001-4000-8000-000000000001
-- Clients:           c1 = ...aa01, c2 = ...aa02, c3 = ...aa03, c4 = ...aa04, c5 = ...aa05
-- Developments:      d1 = ...bb01, d2 = ...bb02, d3 = ...bb03
-- Lots:              ...cc01 a ...cc14
-- ClientLots:        ...dd01 a ...dd04
-- Invoices:          ...ee01 a ...ee19
-- ServiceTypes:      ...ff01 a ...ff07
-- ServiceOrders:     ...ab01 a ...ab06
-- Referrals:         ...ac01 a ...ac03

-- ---------------------------------------------------------------------------
-- 1. COMPANY
-- ---------------------------------------------------------------------------

INSERT INTO companies (id, name, slug, settings, status) VALUES
(
    'a1b2c3d4-0001-4000-8000-000000000001',
    'Cleide Silva Loteamentos',
    'cleide-silva',
    '{"theme": "default", "timezone": "America/Sao_Paulo"}'::jsonb,
    'active'
);

-- ---------------------------------------------------------------------------
-- 2. PROFILES (vinculados aos auth.users do Supabase)
-- ---------------------------------------------------------------------------

-- Admin (super_admin) – usa o ID do auth.users
INSERT INTO profiles (id, company_id, role, full_name, cpf_cnpj, phone, email) VALUES
(
    'db79fbda-8ecd-49ae-b590-0dea1a5f26ad',
    'a1b2c3d4-0001-4000-8000-000000000001',
    'super_admin',
    'Nickson Aleixo',
    '12345678900',
    '11999990000',
    'nacs.promoter@gmail.com'
);

-- Cliente – usa o ID do auth.users
INSERT INTO profiles (id, company_id, role, full_name, cpf_cnpj, phone, email) VALUES
(
    '00df9257-e938-4105-86a1-8bfb98d2ab67',
    'a1b2c3d4-0001-4000-8000-000000000001',
    'client',
    'Cliente Teste',
    '98765432100',
    '11988880000',
    'testecliente@teste.com'
);

-- Company admin (segundo admin da empresa)
INSERT INTO profiles (id, company_id, role, full_name, cpf_cnpj, phone, email) VALUES
(
    'a1b2c3d4-0002-4000-8000-000000000002',
    'a1b2c3d4-0001-4000-8000-000000000001',
    'company_admin',
    'Maria Administradora',
    '11122233344',
    '11977770000',
    'maria@cleidesilva.com'
);

-- ---------------------------------------------------------------------------
-- 3. CLIENTS
-- ---------------------------------------------------------------------------

INSERT INTO clients (id, company_id, profile_id, email, full_name, cpf_cnpj, phone, address, documents, status, asaas_customer_id, created_by) VALUES
(
    '00000000-0000-4000-a000-00000000aa01',
    'a1b2c3d4-0001-4000-8000-000000000001',
    '00df9257-e938-4105-86a1-8bfb98d2ab67',
    'testecliente@teste.com',
    'Cliente Teste',
    '98765432100',
    '11988880000',
    '{"street": "Rua das Flores", "number": "123", "city": "São Paulo", "state": "SP", "zip": "01001-000"}'::jsonb,
    '[]'::jsonb,
    'active',
    NULL,
    'db79fbda-8ecd-49ae-b590-0dea1a5f26ad'
),
(
    '00000000-0000-4000-a000-00000000aa02',
    'a1b2c3d4-0001-4000-8000-000000000001',
    NULL,
    'joao.silva@email.com',
    'João Silva',
    '22233344455',
    '11966660000',
    '{"street": "Av. Paulista", "number": "1000", "city": "São Paulo", "state": "SP", "zip": "01310-100"}'::jsonb,
    '[]'::jsonb,
    'active',
    NULL,
    'db79fbda-8ecd-49ae-b590-0dea1a5f26ad'
),
(
    '00000000-0000-4000-a000-00000000aa03',
    'a1b2c3d4-0001-4000-8000-000000000001',
    NULL,
    'ana.santos@email.com',
    'Ana Santos',
    '55566677788',
    '11955550000',
    '{"street": "Rua Augusta", "number": "500", "city": "São Paulo", "state": "SP", "zip": "01305-000"}'::jsonb,
    '[]'::jsonb,
    'active',
    NULL,
    'db79fbda-8ecd-49ae-b590-0dea1a5f26ad'
),
(
    '00000000-0000-4000-a000-00000000aa04',
    'a1b2c3d4-0001-4000-8000-000000000001',
    NULL,
    'carlos.oliveira@email.com',
    'Carlos Oliveira',
    '99988877766',
    '11944440000',
    '{"street": "Rua XV de Novembro", "number": "200", "city": "Curitiba", "state": "PR", "zip": "80020-310"}'::jsonb,
    '[]'::jsonb,
    'defaulter',
    NULL,
    'db79fbda-8ecd-49ae-b590-0dea1a5f26ad'
),
(
    '00000000-0000-4000-a000-00000000aa05',
    'a1b2c3d4-0001-4000-8000-000000000001',
    NULL,
    'patricia.lima@email.com',
    'Patricia Lima',
    '33344455566',
    '11933330000',
    '{"street": "Rua Copacabana", "number": "88", "city": "Rio de Janeiro", "state": "RJ", "zip": "22050-002"}'::jsonb,
    '[]'::jsonb,
    'inactive',
    NULL,
    'db79fbda-8ecd-49ae-b590-0dea1a5f26ad'
);

-- ---------------------------------------------------------------------------
-- 4. DEVELOPMENTS (empreendimentos)
-- ---------------------------------------------------------------------------

INSERT INTO developments (id, company_id, name, description, location, documents) VALUES
(
    '00000000-0000-4000-b000-00000000bb01',
    'a1b2c3d4-0001-4000-8000-000000000001',
    'Residencial Parque das Águas',
    'Loteamento residencial com infraestrutura completa, próximo ao centro. Área verde preservada, ruas asfaltadas, rede de água e esgoto.',
    'Rodovia SP-100, km 25 - Campinas/SP',
    '{}'::jsonb
),
(
    '00000000-0000-4000-b000-00000000bb02',
    'a1b2c3d4-0001-4000-8000-000000000001',
    'Jardim dos Ipês',
    'Condomínio fechado com segurança 24h, área de lazer completa e lotes amplos. Ideal para famílias.',
    'Av. das Nações, 1500 - Sorocaba/SP',
    '{}'::jsonb
),
(
    '00000000-0000-4000-b000-00000000bb03',
    'a1b2c3d4-0001-4000-8000-000000000001',
    'Vila Verde Eco Residence',
    'Empreendimento sustentável com captação de água pluvial, energia solar e trilhas ecológicas.',
    'Estrada Municipal, km 8 - Atibaia/SP',
    '{}'::jsonb
);

-- ---------------------------------------------------------------------------
-- 5. LOTS (lotes)
-- ---------------------------------------------------------------------------

INSERT INTO lots (id, company_id, development_id, lot_number, block, area_m2, price, status) VALUES
-- Parque das Águas
('00000000-0000-4000-c000-00000000cc01', 'a1b2c3d4-0001-4000-8000-000000000001', '00000000-0000-4000-b000-00000000bb01', '01', 'A', 250.00, 85000.00, 'sold'),
('00000000-0000-4000-c000-00000000cc02', 'a1b2c3d4-0001-4000-8000-000000000001', '00000000-0000-4000-b000-00000000bb01', '02', 'A', 300.00, 95000.00, 'sold'),
('00000000-0000-4000-c000-00000000cc03', 'a1b2c3d4-0001-4000-8000-000000000001', '00000000-0000-4000-b000-00000000bb01', '03', 'A', 275.00, 90000.00, 'reserved'),
('00000000-0000-4000-c000-00000000cc04', 'a1b2c3d4-0001-4000-8000-000000000001', '00000000-0000-4000-b000-00000000bb01', '04', 'B', 320.00, 105000.00, 'available'),
('00000000-0000-4000-c000-00000000cc05', 'a1b2c3d4-0001-4000-8000-000000000001', '00000000-0000-4000-b000-00000000bb01', '05', 'B', 280.00, 92000.00, 'available'),
('00000000-0000-4000-c000-00000000cc06', 'a1b2c3d4-0001-4000-8000-000000000001', '00000000-0000-4000-b000-00000000bb01', '06', 'B', 310.00, 100000.00, 'available'),
-- Jardim dos Ipês
('00000000-0000-4000-c000-00000000cc07', 'a1b2c3d4-0001-4000-8000-000000000001', '00000000-0000-4000-b000-00000000bb02', '01', 'A', 400.00, 150000.00, 'sold'),
('00000000-0000-4000-c000-00000000cc08', 'a1b2c3d4-0001-4000-8000-000000000001', '00000000-0000-4000-b000-00000000bb02', '02', 'A', 380.00, 140000.00, 'available'),
('00000000-0000-4000-c000-00000000cc09', 'a1b2c3d4-0001-4000-8000-000000000001', '00000000-0000-4000-b000-00000000bb02', '03', 'B', 420.00, 160000.00, 'available'),
('00000000-0000-4000-c000-00000000cc0a', 'a1b2c3d4-0001-4000-8000-000000000001', '00000000-0000-4000-b000-00000000bb02', '04', 'B', 350.00, 135000.00, 'available'),
-- Vila Verde
('00000000-0000-4000-c000-00000000cc0b', 'a1b2c3d4-0001-4000-8000-000000000001', '00000000-0000-4000-b000-00000000bb03', '01', 'A', 500.00, 200000.00, 'sold'),
('00000000-0000-4000-c000-00000000cc0c', 'a1b2c3d4-0001-4000-8000-000000000001', '00000000-0000-4000-b000-00000000bb03', '02', 'A', 480.00, 190000.00, 'available'),
('00000000-0000-4000-c000-00000000cc0d', 'a1b2c3d4-0001-4000-8000-000000000001', '00000000-0000-4000-b000-00000000bb03', '03', 'B', 520.00, 210000.00, 'available'),
('00000000-0000-4000-c000-00000000cc0e', 'a1b2c3d4-0001-4000-8000-000000000001', '00000000-0000-4000-b000-00000000bb03', '04', 'B', 550.00, 220000.00, 'available');

-- ---------------------------------------------------------------------------
-- 6. CLIENT_LOTS (compras)
-- ---------------------------------------------------------------------------

INSERT INTO client_lots (id, company_id, client_id, lot_id, purchase_date, total_value, payment_plan, status) VALUES
-- Cliente Teste comprou lote 01/A do Parque das Águas (pago em dia)
(
    '00000000-0000-4000-d000-00000000dd01',
    'a1b2c3d4-0001-4000-8000-000000000001',
    '00000000-0000-4000-a000-00000000aa01',
    '00000000-0000-4000-c000-00000000cc01',
    '2025-06-15',
    85000.00,
    '{"installments": 12, "down_payment": 10000, "monthly_value": 6250}'::jsonb,
    'active'
),
-- João Silva comprou lote 02/A do Parque das Águas
(
    '00000000-0000-4000-d000-00000000dd02',
    'a1b2c3d4-0001-4000-8000-000000000001',
    '00000000-0000-4000-a000-00000000aa02',
    '00000000-0000-4000-c000-00000000cc02',
    '2025-07-01',
    95000.00,
    '{"installments": 24, "down_payment": 15000, "monthly_value": 3333.33}'::jsonb,
    'active'
),
-- Ana Santos comprou lote 01/A do Jardim dos Ipês
(
    '00000000-0000-4000-d000-00000000dd03',
    'a1b2c3d4-0001-4000-8000-000000000001',
    '00000000-0000-4000-a000-00000000aa03',
    '00000000-0000-4000-c000-00000000cc07',
    '2025-08-10',
    150000.00,
    '{"installments": 36, "down_payment": 30000, "monthly_value": 3333.33}'::jsonb,
    'active'
),
-- Carlos Oliveira (inadimplente) comprou lote 01/A da Vila Verde
(
    '00000000-0000-4000-d000-00000000dd04',
    'a1b2c3d4-0001-4000-8000-000000000001',
    '00000000-0000-4000-a000-00000000aa04',
    '00000000-0000-4000-c000-00000000cc0b',
    '2025-03-01',
    200000.00,
    '{"installments": 48, "down_payment": 20000, "monthly_value": 3750}'::jsonb,
    'active'
);

-- ---------------------------------------------------------------------------
-- 7. INVOICES (boletos/parcelas) – mix de status para testar dashboard
-- ---------------------------------------------------------------------------

-- Cliente Teste – 6 parcelas (4 pagas, 1 pendente, 1 futura)
INSERT INTO invoices (id, company_id, client_lot_id, due_date, amount, installment_number, status, paid_at) VALUES
('00000000-0000-4000-e000-00000000ee01', 'a1b2c3d4-0001-4000-8000-000000000001', '00000000-0000-4000-d000-00000000dd01', '2025-07-15', 6250.00, 1, 'paid', '2025-07-14 10:00:00+00'),
('00000000-0000-4000-e000-00000000ee02', 'a1b2c3d4-0001-4000-8000-000000000001', '00000000-0000-4000-d000-00000000dd01', '2025-08-15', 6250.00, 2, 'paid', '2025-08-13 14:30:00+00'),
('00000000-0000-4000-e000-00000000ee03', 'a1b2c3d4-0001-4000-8000-000000000001', '00000000-0000-4000-d000-00000000dd01', '2025-09-15', 6250.00, 3, 'paid', '2025-09-15 09:00:00+00'),
('00000000-0000-4000-e000-00000000ee04', 'a1b2c3d4-0001-4000-8000-000000000001', '00000000-0000-4000-d000-00000000dd01', '2025-10-15', 6250.00, 4, 'paid', '2025-10-12 16:00:00+00'),
('00000000-0000-4000-e000-00000000ee05', 'a1b2c3d4-0001-4000-8000-000000000001', '00000000-0000-4000-d000-00000000dd01', '2025-11-15', 6250.00, 5, 'pending', NULL),
('00000000-0000-4000-e000-00000000ee06', 'a1b2c3d4-0001-4000-8000-000000000001', '00000000-0000-4000-d000-00000000dd01', '2025-12-15', 6250.00, 6, 'pending', NULL);

-- João Silva – 4 parcelas (2 pagas, 1 vencida, 1 pendente)
INSERT INTO invoices (id, company_id, client_lot_id, due_date, amount, installment_number, status, paid_at) VALUES
('00000000-0000-4000-e000-00000000ee07', 'a1b2c3d4-0001-4000-8000-000000000001', '00000000-0000-4000-d000-00000000dd02', '2025-08-01', 3333.33, 1, 'paid', '2025-07-30 11:00:00+00'),
('00000000-0000-4000-e000-00000000ee08', 'a1b2c3d4-0001-4000-8000-000000000001', '00000000-0000-4000-d000-00000000dd02', '2025-09-01', 3333.33, 2, 'paid', '2025-08-29 15:00:00+00'),
('00000000-0000-4000-e000-00000000ee09', 'a1b2c3d4-0001-4000-8000-000000000001', '00000000-0000-4000-d000-00000000dd02', '2025-10-01', 3333.33, 3, 'overdue', NULL),
('00000000-0000-4000-e000-00000000ee0a', 'a1b2c3d4-0001-4000-8000-000000000001', '00000000-0000-4000-d000-00000000dd02', '2025-11-01', 3333.33, 4, 'pending', NULL);

-- Ana Santos – 3 parcelas (1 paga, 2 pendentes)
INSERT INTO invoices (id, company_id, client_lot_id, due_date, amount, installment_number, status, paid_at) VALUES
('00000000-0000-4000-e000-00000000ee0b', 'a1b2c3d4-0001-4000-8000-000000000001', '00000000-0000-4000-d000-00000000dd03', '2025-09-10', 3333.33, 1, 'paid', '2025-09-08 10:00:00+00'),
('00000000-0000-4000-e000-00000000ee0c', 'a1b2c3d4-0001-4000-8000-000000000001', '00000000-0000-4000-d000-00000000dd03', '2025-10-10', 3333.33, 2, 'pending', NULL),
('00000000-0000-4000-e000-00000000ee0d', 'a1b2c3d4-0001-4000-8000-000000000001', '00000000-0000-4000-d000-00000000dd03', '2025-11-10', 3333.33, 3, 'pending', NULL);

-- Carlos Oliveira (inadimplente) – 6 parcelas (1 paga, 5 vencidas)
INSERT INTO invoices (id, company_id, client_lot_id, due_date, amount, installment_number, status, paid_at) VALUES
('00000000-0000-4000-e000-00000000ee0e', 'a1b2c3d4-0001-4000-8000-000000000001', '00000000-0000-4000-d000-00000000dd04', '2025-04-01', 3750.00, 1, 'paid', '2025-03-30 12:00:00+00'),
('00000000-0000-4000-e000-00000000ee0f', 'a1b2c3d4-0001-4000-8000-000000000001', '00000000-0000-4000-d000-00000000dd04', '2025-05-01', 3750.00, 2, 'overdue', NULL),
('00000000-0000-4000-e000-00000000ee10', 'a1b2c3d4-0001-4000-8000-000000000001', '00000000-0000-4000-d000-00000000dd04', '2025-06-01', 3750.00, 3, 'overdue', NULL),
('00000000-0000-4000-e000-00000000ee11', 'a1b2c3d4-0001-4000-8000-000000000001', '00000000-0000-4000-d000-00000000dd04', '2025-07-01', 3750.00, 4, 'overdue', NULL),
('00000000-0000-4000-e000-00000000ee12', 'a1b2c3d4-0001-4000-8000-000000000001', '00000000-0000-4000-d000-00000000dd04', '2025-08-01', 3750.00, 5, 'overdue', NULL),
('00000000-0000-4000-e000-00000000ee13', 'a1b2c3d4-0001-4000-8000-000000000001', '00000000-0000-4000-d000-00000000dd04', '2025-09-01', 3750.00, 6, 'overdue', NULL);

-- ---------------------------------------------------------------------------
-- 8. SERVICE_TYPES
-- ---------------------------------------------------------------------------

INSERT INTO service_types (id, company_id, name, description, base_price, is_active) VALUES
('00000000-0000-4000-f000-00000000ff01', 'a1b2c3d4-0001-4000-8000-000000000001', 'Limpeza de Terreno', 'Roçada, capina e limpeza geral do lote', 350.00, true),
('00000000-0000-4000-f000-00000000ff02', 'a1b2c3d4-0001-4000-8000-000000000001', 'Cercamento', 'Instalação de cerca no perímetro do lote', 1200.00, true),
('00000000-0000-4000-f000-00000000ff03', 'a1b2c3d4-0001-4000-8000-000000000001', 'Terraplanagem', 'Nivelamento e preparação do solo para construção', 2500.00, true),
('00000000-0000-4000-f000-00000000ff04', 'a1b2c3d4-0001-4000-8000-000000000001', 'Muro de Arrimo', 'Construção de muro de contenção', 4500.00, true),
('00000000-0000-4000-f000-00000000ff05', 'a1b2c3d4-0001-4000-8000-000000000001', 'Ligação de Água', 'Solicitação e instalação de ponto de água', 800.00, true),
('00000000-0000-4000-f000-00000000ff06', 'a1b2c3d4-0001-4000-8000-000000000001', 'Ligação de Energia', 'Solicitação e instalação de ponto de energia elétrica', 650.00, true),
('00000000-0000-4000-f000-00000000ff07', 'a1b2c3d4-0001-4000-8000-000000000001', 'Projeto Arquitetônico', 'Elaboração de projeto residencial completo', 8000.00, false);

-- ---------------------------------------------------------------------------
-- 9. SERVICE_ORDERS (ordens de serviço – vários status)
-- ---------------------------------------------------------------------------

INSERT INTO service_orders (id, company_id, client_id, lot_id, service_type_id, requested_date, execution_date, status, cost, revenue, notes) VALUES
-- Cliente Teste – limpeza concluída
(
    '00000000-0000-4000-ab00-00000000ab01',
    'a1b2c3d4-0001-4000-8000-000000000001',
    '00000000-0000-4000-a000-00000000aa01',
    '00000000-0000-4000-c000-00000000cc01',
    '00000000-0000-4000-f000-00000000ff01',
    '2025-08-01', '2025-08-05',
    'completed', 200.00, 350.00,
    'Limpeza realizada com sucesso. Terreno pronto para cercamento.'
),
-- Cliente Teste – cercamento em andamento
(
    '00000000-0000-4000-ab00-00000000ab02',
    'a1b2c3d4-0001-4000-8000-000000000001',
    '00000000-0000-4000-a000-00000000aa01',
    '00000000-0000-4000-c000-00000000cc01',
    '00000000-0000-4000-f000-00000000ff02',
    '2025-09-10', NULL,
    'in_progress', 800.00, 1200.00,
    'Material comprado. Instalação prevista para próxima semana.'
),
-- João Silva – terraplanagem aprovada
(
    '00000000-0000-4000-ab00-00000000ab03',
    'a1b2c3d4-0001-4000-8000-000000000001',
    '00000000-0000-4000-a000-00000000aa02',
    '00000000-0000-4000-c000-00000000cc02',
    '00000000-0000-4000-f000-00000000ff03',
    '2025-09-20', NULL,
    'approved', 0.00, 2500.00,
    'Aguardando maquinário disponível.'
),
-- Ana Santos – ligação de água solicitada
(
    '00000000-0000-4000-ab00-00000000ab04',
    'a1b2c3d4-0001-4000-8000-000000000001',
    '00000000-0000-4000-a000-00000000aa03',
    '00000000-0000-4000-c000-00000000cc07',
    '00000000-0000-4000-f000-00000000ff05',
    '2025-10-01', NULL,
    'requested', 0.00, 800.00,
    NULL
),
-- Ana Santos – limpeza concluída
(
    '00000000-0000-4000-ab00-00000000ab05',
    'a1b2c3d4-0001-4000-8000-000000000001',
    '00000000-0000-4000-a000-00000000aa03',
    '00000000-0000-4000-c000-00000000cc07',
    '00000000-0000-4000-f000-00000000ff01',
    '2025-08-20', '2025-08-22',
    'completed', 180.00, 350.00,
    'Terreno limpo e pronto.'
),
-- Carlos Oliveira – cercamento cancelado (inadimplente)
(
    '00000000-0000-4000-ab00-00000000ab06',
    'a1b2c3d4-0001-4000-8000-000000000001',
    '00000000-0000-4000-a000-00000000aa04',
    '00000000-0000-4000-c000-00000000cc0b',
    '00000000-0000-4000-f000-00000000ff02',
    '2025-06-15', NULL,
    'cancelled', 0.00, 0.00,
    'Cancelado por inadimplência do cliente.'
);

-- ---------------------------------------------------------------------------
-- 10. REFERRALS (indicações)
-- ---------------------------------------------------------------------------

INSERT INTO referrals (id, company_id, referrer_client_id, referred_name, referred_phone, referred_email, status) VALUES
(
    '00000000-0000-4000-ac00-00000000ac01',
    'a1b2c3d4-0001-4000-8000-000000000001',
    '00000000-0000-4000-a000-00000000aa01',
    'Pedro Mendes',
    '11922220000',
    'pedro.mendes@email.com',
    'contacted'
),
(
    '00000000-0000-4000-ac00-00000000ac02',
    'a1b2c3d4-0001-4000-8000-000000000001',
    '00000000-0000-4000-a000-00000000aa01',
    'Fernanda Costa',
    '11911110000',
    'fernanda.costa@email.com',
    'converted'
),
(
    '00000000-0000-4000-ac00-00000000ac03',
    'a1b2c3d4-0001-4000-8000-000000000001',
    '00000000-0000-4000-a000-00000000aa03',
    'Roberto Almeida',
    '11900000000',
    NULL,
    'pending'
);

-- ---------------------------------------------------------------------------
-- 11. AUDIT_LOGS (exemplo de registros)
-- ---------------------------------------------------------------------------

INSERT INTO audit_logs (user_id, company_id, table_name, operation, resource_id, detail, ip_address, user_agent) VALUES
('db79fbda-8ecd-49ae-b590-0dea1a5f26ad', 'a1b2c3d4-0001-4000-8000-000000000001', 'clients', 'CREATE', '00000000-0000-4000-a000-00000000aa01', 'Criou cliente: Cliente Teste', '127.0.0.1', 'CSApp/1.0'),
('db79fbda-8ecd-49ae-b590-0dea1a5f26ad', 'a1b2c3d4-0001-4000-8000-000000000001', 'client_lots', 'CREATE', '00000000-0000-4000-d000-00000000dd01', 'Atribuiu lote 01/A ao Cliente Teste', '127.0.0.1', 'CSApp/1.0'),
('db79fbda-8ecd-49ae-b590-0dea1a5f26ad', 'a1b2c3d4-0001-4000-8000-000000000001', 'clients', 'UPDATE', '00000000-0000-4000-a000-00000000aa04', 'Status alterado para defaulter', '127.0.0.1', 'CSApp/1.0');
