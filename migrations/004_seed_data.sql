-- ============================================
-- Real Estate Management System - Seed Data
-- Migration 004: Initial data for testing
-- ============================================

-- NOTE: Run this ONLY in development/sandbox environments
-- Do NOT run in production

-- ============================================
-- SAMPLE SERVICE TYPES
-- ============================================

INSERT INTO service_types (name, description, base_price, is_active) VALUES
    ('Limpeza de Terreno', 'Serviço de limpeza e capina do terreno', 500.00, true),
    ('Demarcação de Lote', 'Demarcação física dos limites do lote', 300.00, true),
    ('Muro de Divisa', 'Construção de muro nas divisas do terreno', 5000.00, true),
    ('Terraplanagem', 'Nivelamento e preparação do terreno para construção', 3000.00, true),
    ('Instalação de Água', 'Instalação do ponto de água no lote', 800.00, true),
    ('Instalação de Energia', 'Instalação do ponto de energia elétrica', 1200.00, true),
    ('Projeto Arquitetônico', 'Elaboração de projeto arquitetônico residencial', 4000.00, true),
    ('Vistoria Técnica', 'Vistoria técnica do terreno e documentação', 400.00, true)
ON CONFLICT DO NOTHING;

-- ============================================
-- SAMPLE DEVELOPMENT (Empreendimento)
-- ============================================

INSERT INTO developments (id, name, description, location) VALUES
    ('11111111-1111-1111-1111-111111111111', 
     'Residencial Jardim das Flores', 
     'Loteamento residencial com infraestrutura completa, área de lazer e segurança 24h.', 
     'Rodovia BR-101, Km 45, Cidade Exemplo - Estado')
ON CONFLICT (id) DO NOTHING;

-- ============================================
-- SAMPLE LOTS
-- ============================================

INSERT INTO lots (development_id, lot_number, block, area_m2, price, status) VALUES
    ('11111111-1111-1111-1111-111111111111', '01', 'A', 300.00, 45000.00, 'available'),
    ('11111111-1111-1111-1111-111111111111', '02', 'A', 320.00, 48000.00, 'available'),
    ('11111111-1111-1111-1111-111111111111', '03', 'A', 280.00, 42000.00, 'available'),
    ('11111111-1111-1111-1111-111111111111', '04', 'A', 350.00, 52500.00, 'available'),
    ('11111111-1111-1111-1111-111111111111', '05', 'A', 400.00, 60000.00, 'available'),
    ('11111111-1111-1111-1111-111111111111', '01', 'B', 300.00, 45000.00, 'available'),
    ('11111111-1111-1111-1111-111111111111', '02', 'B', 320.00, 48000.00, 'available'),
    ('11111111-1111-1111-1111-111111111111', '03', 'B', 280.00, 42000.00, 'available'),
    ('11111111-1111-1111-1111-111111111111', '04', 'B', 350.00, 52500.00, 'available'),
    ('11111111-1111-1111-1111-111111111111', '05', 'B', 400.00, 60000.00, 'reserved'),
    ('11111111-1111-1111-1111-111111111111', '01', 'C', 500.00, 75000.00, 'available'),
    ('11111111-1111-1111-1111-111111111111', '02', 'C', 500.00, 75000.00, 'sold')
ON CONFLICT DO NOTHING;

-- ============================================
-- NOTE: Admin user must be created through the API
-- or Supabase Dashboard, as it requires auth.users entry
-- ============================================

-- Example of how to create admin profile after creating auth user:
-- INSERT INTO profiles (id, full_name, cpf_cnpj, phone, role) VALUES
--     ('user-uuid-from-auth', 'Admin User', '12345678901', '11999999999', 'admin');
