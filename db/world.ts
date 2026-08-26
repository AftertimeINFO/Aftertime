import { env } from "cloudflare:workers";

type Row = Record<string, string | number | null>;

const schemaStatements = [
  `CREATE TABLE IF NOT EXISTS entities (
    id TEXT PRIMARY KEY, kind TEXT NOT NULL, level TEXT NOT NULL, name TEXT NOT NULL,
    symbol TEXT, description TEXT, jurisdiction TEXT, valid_from TEXT, valid_to TEXT
  )`,
  `CREATE TABLE IF NOT EXISTS relations (
    id TEXT PRIMARY KEY, subject_id TEXT NOT NULL, predicate TEXT NOT NULL, object_id TEXT NOT NULL,
    coefficient REAL, unit TEXT, confidence REAL NOT NULL DEFAULT 1, source_id TEXT,
    valid_from TEXT, valid_to TEXT
  )`,
  `CREATE TABLE IF NOT EXISTS sources (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, url TEXT NOT NULL, license TEXT, retrieved_at TEXT NOT NULL
  )`,
  `CREATE TABLE IF NOT EXISTS external_identities (
    id TEXT PRIMARY KEY, entity_id TEXT NOT NULL, namespace TEXT NOT NULL, external_id TEXT NOT NULL,
    source_id TEXT NOT NULL, mapping_type TEXT NOT NULL, confidence REAL NOT NULL
  )`,
  `CREATE TABLE IF NOT EXISTS facilities (
    entity_id TEXT PRIMARY KEY, facility_type TEXT NOT NULL, status TEXT NOT NULL,
    latitude REAL, longitude REAL, nominal_capacity REAL, available_capacity REAL,
    capacity_unit TEXT, availability REAL NOT NULL
  )`,
  `CREATE TABLE IF NOT EXISTS capabilities (
    id TEXT PRIMARY KEY, owner_entity_id TEXT NOT NULL, action TEXT NOT NULL, output_entity_id TEXT NOT NULL,
    max_rate REAL NOT NULL, available_rate REAL NOT NULL, unit TEXT NOT NULL,
    confidence REAL NOT NULL, model_version TEXT NOT NULL
  )`,
  `CREATE TABLE IF NOT EXISTS dependencies (
    id TEXT PRIMARY KEY, capability_id TEXT NOT NULL, dependency_entity_id TEXT NOT NULL,
    dependency_type TEXT NOT NULL, required_amount REAL, unit TEXT,
    current_availability REAL NOT NULL, criticality REAL NOT NULL, recovery_days REAL
  )`,
  `CREATE TABLE IF NOT EXISTS observations (
    id TEXT PRIMARY KEY, subject_entity_id TEXT NOT NULL, property TEXT NOT NULL,
    value REAL NOT NULL, unit TEXT NOT NULL, reality_class TEXT NOT NULL,
    epistemic_status TEXT NOT NULL, valid_time TEXT NOT NULL, recorded_time TEXT NOT NULL,
    source_id TEXT NOT NULL, uncertainty_low REAL, uncertainty_high REAL
  )`,
  `CREATE TABLE IF NOT EXISTS events (
    id TEXT PRIMARY KEY, event_type TEXT NOT NULL, name TEXT NOT NULL, actuality TEXT NOT NULL,
    status TEXT NOT NULL, started_at TEXT NOT NULL, ended_at TEXT, location_entity_id TEXT,
    actor_entity_id TEXT, model_version TEXT
  )`,
  `CREATE TABLE IF NOT EXISTS postings (
    id TEXT PRIMARY KEY, event_id TEXT NOT NULL, entity_id TEXT NOT NULL, role TEXT NOT NULL,
    direction TEXT NOT NULL, quantity REAL NOT NULL, unit TEXT NOT NULL,
    abstraction_level TEXT NOT NULL, source_id TEXT
  )`,
  `CREATE TABLE IF NOT EXISTS scenarios (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT NOT NULL, horizon TEXT NOT NULL,
    gas_availability REAL NOT NULL, grid_availability REAL NOT NULL,
    logistics_availability REAL NOT NULL, workforce_availability REAL NOT NULL,
    demand_growth REAL NOT NULL, probability REAL NOT NULL, model_version TEXT NOT NULL
  )`,
  `CREATE TABLE IF NOT EXISTS model_runs (
    id TEXT PRIMARY KEY, scenario_id TEXT NOT NULL, run_at TEXT NOT NULL, model_version TEXT NOT NULL,
    expected_output REAL NOT NULL, low_output REAL NOT NULL, high_output REAL NOT NULL,
    unit TEXT NOT NULL, confidence REAL NOT NULL, limiting_factor TEXT NOT NULL
  )`,
  `CREATE TABLE IF NOT EXISTS process_models (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, action TEXT NOT NULL, owner_entity_id TEXT NOT NULL,
    model_version TEXT NOT NULL, duration_hours REAL NOT NULL, yield_factor REAL NOT NULL,
    valid_from TEXT NOT NULL, source_id TEXT NOT NULL
  )`,
  `CREATE TABLE IF NOT EXISTS process_flows (
    id TEXT PRIMARY KEY, process_id TEXT NOT NULL, entity_id TEXT NOT NULL, direction TEXT NOT NULL,
    role TEXT NOT NULL, amount_per_unit REAL NOT NULL, unit TEXT NOT NULL, uncertainty REAL NOT NULL
  )`,
  `CREATE TABLE IF NOT EXISTS inventory_lots (
    id TEXT PRIMARY KEY, entity_id TEXT NOT NULL, container_entity_id TEXT NOT NULL,
    owner_entity_id TEXT NOT NULL, quantity REAL NOT NULL, unit TEXT NOT NULL,
    quality_status TEXT NOT NULL, observed_at TEXT NOT NULL, source_id TEXT NOT NULL
  )`,
  `CREATE TABLE IF NOT EXISTS transport_routes (
    id TEXT PRIMARY KEY, origin_entity_id TEXT NOT NULL, destination_entity_id TEXT NOT NULL,
    mode TEXT NOT NULL, distance_km REAL NOT NULL, capacity_per_day REAL NOT NULL,
    capacity_unit TEXT NOT NULL, duration_hours REAL NOT NULL, availability REAL NOT NULL,
    loss_factor REAL NOT NULL, recovery_hours REAL NOT NULL
  )`,
  `CREATE TABLE IF NOT EXISTS circuit_runs (
    id TEXT PRIMARY KEY, scenario_id TEXT NOT NULL, model_version TEXT NOT NULL,
    target_quantity REAL NOT NULL, delivered_quantity REAL NOT NULL,
    lower_quantity REAL NOT NULL, upper_quantity REAL NOT NULL, unit TEXT NOT NULL,
    bottleneck TEXT NOT NULL, confidence REAL NOT NULL, expected_hours REAL NOT NULL,
    conservation_error REAL NOT NULL, run_at TEXT NOT NULL
  )`,
  `CREATE TABLE IF NOT EXISTS interventions (
    id TEXT PRIMARY KEY, circuit_run_id TEXT NOT NULL, action TEXT NOT NULL,
    target_entity_id TEXT NOT NULL, lead_time_hours REAL NOT NULL,
    recovered_quantity REAL NOT NULL, unit TEXT NOT NULL, status TEXT NOT NULL,
    rationale TEXT NOT NULL
  )`,
  `CREATE TABLE IF NOT EXISTS technologies (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, category TEXT NOT NULL,
    input_form TEXT NOT NULL, output_form TEXT NOT NULL, efficiency REAL NOT NULL,
    useful_effect TEXT NOT NULL, waste_effect TEXT NOT NULL, model_version TEXT NOT NULL
  )`,
  `CREATE TABLE IF NOT EXISTS principle_systems (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, system_type TEXT NOT NULL,
    purpose TEXT NOT NULL, input_form TEXT NOT NULL, output_form TEXT NOT NULL,
    model_version TEXT NOT NULL
  )`,
  `CREATE TABLE IF NOT EXISTS end_products (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, product_type TEXT NOT NULL,
    rated_power_kw REAL NOT NULL, transformation TEXT NOT NULL,
    useful_output TEXT NOT NULL, waste_output TEXT NOT NULL, coefficient REAL NOT NULL
  )`,
  `CREATE TABLE IF NOT EXISTS test_models (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT NOT NULL,
    status TEXT NOT NULL, duration_hours REAL NOT NULL, model_version TEXT NOT NULL
  )`,
  `CREATE TABLE IF NOT EXISTS test_model_components (
    id TEXT PRIMARY KEY, test_model_id TEXT NOT NULL, component_kind TEXT NOT NULL,
    component_id TEXT NOT NULL, sequence_no INTEGER NOT NULL, branch TEXT NOT NULL,
    quantity REAL NOT NULL
  )`,
  `CREATE TABLE IF NOT EXISTS territorial_units (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, unit_type TEXT NOT NULL,
    country_code TEXT, centroid_lat REAL, centroid_lon REAL,
    location_precision TEXT NOT NULL, estimated_users INTEGER,
    user_count_uncertainty REAL, epistemic_status TEXT NOT NULL, source_id TEXT NOT NULL
  )`,
  `CREATE TABLE IF NOT EXISTS real_systems (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, system_type TEXT NOT NULL,
    principle_system_id TEXT NOT NULL, latitude REAL, longitude REAL,
    location_precision_m REAL, territory_id TEXT, actuality TEXT NOT NULL,
    status TEXT NOT NULL, source_id TEXT NOT NULL
  )`,
];

const seedStatements = [
  `INSERT OR IGNORE INTO sources VALUES
    ('src-iea','IEA Ammonia Technology Roadmap','https://www.iea.org/reports/ammonia-technology-roadmap','CC BY 4.0','2026-07-29'),
    ('src-faostat','FAOSTAT Fertilizers by Nutrient','https://www.fao.org/faostat/','FAO terms','2026-07-29'),
    ('src-chebi','ChEBI','https://www.ebi.ac.uk/chebi/','CC BY 4.0','2026-07-29'),
    ('src-orb','ORB pilot model','https://orb-srp-prototype.neokkv.chatgpt.site','Project data','2026-07-29')`,
  `INSERT OR IGNORE INTO entities VALUES
    ('country-ua','state','institutional','Украина','UA','Институциональная граница пилотного контура','UA','1991-08-24',NULL),
    ('company-azot','company','institutional','ORB Nitrogen Operations',NULL,'Демонстрационный оператор производственного контура','UA','2026-01-01',NULL),
    ('plant-cherkasy','facility','object','Черкасский азотный узел',NULL,'Модель производственного узла для проверки архитектуры','UA','2026-01-01',NULL),
    ('line-ammonia-1','production_line','object','Линия синтеза аммиака №1',NULL,'Критическая производственная линия','UA','2026-01-01',NULL),
    ('network-gas','infrastructure','object','Газоснабжение',NULL,'Вход природного газа в производственный контур','UA','2026-01-01',NULL),
    ('network-grid','infrastructure','object','Энергосистема',NULL,'Электроснабжение производственного контура','UA','2026-01-01',NULL),
    ('network-rail','infrastructure','object','Железнодорожная сеть',NULL,'Доставка удобрений в аграрные регионы','UA','2026-01-01',NULL),
    ('tank-ammonia-1','storage_asset','object','Резервуар аммиака R-01',NULL,'Промежуточное хранение партии аммиака','UA','2026-01-01',NULL),
    ('rail-tank-1','transport_asset','object','Железнодорожная цистерна C-01',NULL,'Перевозка партии аммиака','UA','2026-01-01',NULL),
    ('warehouse-poltava','warehouse','object','Полтавский региональный склад',NULL,'Точка доставки тестовой партии','UA','2026-01-01',NULL),
    ('network-water','infrastructure','object','Промышленное водоснабжение',NULL,'Вода для водородного и парового контура','UA','2026-01-01',NULL),
    ('workforce-ammonia','workforce_pool','agent','Персонал аммиачного производства',NULL,'Агрегированный пул обязательных компетенций','UA','2026-01-01',NULL),
    ('n-atom','atom','atomic','Азот','N','Атомарное представление азота',NULL,NULL,NULL),
    ('h-atom','atom','atomic','Водород','H','Атомарное представление водорода',NULL,NULL,NULL),
    ('n2','chemical_entity','chemical','Азот молекулярный','N₂','Атмосферный азот',NULL,NULL,NULL),
    ('h2','chemical_entity','chemical','Водород','H₂','Технологический водород',NULL,NULL,NULL),
    ('nh3','chemical_entity','chemical','Аммиак','NH₃','Базовая химическая сущность азотного контура',NULL,NULL,NULL),
    ('urea','material','material','Карбамид','CO(NH₂)₂','Азотное удобрение',NULL,NULL,NULL),
    ('grain','material','material','Зерно','🌾','Агрегированный продукт растениеводства',NULL,NULL,NULL)`,
  `INSERT OR IGNORE INTO external_identities VALUES
    ('ext-n2-chebi','n2','ChEBI','CHEBI:17997','src-chebi','exact_match',1),
    ('ext-h2-chebi','h2','ChEBI','CHEBI:18276','src-chebi','exact_match',1),
    ('ext-nh3-chebi','nh3','ChEBI','CHEBI:16134','src-chebi','exact_match',1),
    ('ext-urea-chebi','urea','ChEBI','CHEBI:16199','src-chebi','close_match',0.95)`,
  `INSERT OR IGNORE INTO relations VALUES
    ('rel-country-plant','plant-cherkasy','located_in','country-ua',NULL,NULL,1,'src-orb','2026-01-01',NULL),
    ('rel-company-plant','company-azot','operates','plant-cherkasy',NULL,NULL,1,'src-orb','2026-01-01',NULL),
    ('rel-plant-line','plant-cherkasy','contains','line-ammonia-1',NULL,NULL,1,'src-orb','2026-01-01',NULL),
    ('rel-n2-n','n2','composed_of','n-atom',2,'atom/mol',1,'src-chebi',NULL,NULL),
    ('rel-h2-h','h2','composed_of','h-atom',2,'atom/mol',1,'src-chebi',NULL,NULL),
    ('rel-nh3-n','nh3','composed_of','n-atom',1,'atom/mol',1,'src-chebi',NULL,NULL),
    ('rel-nh3-h','nh3','composed_of','h-atom',3,'atom/mol',1,'src-chebi',NULL,NULL),
    ('rel-urea-n','urea','contains_element','n-atom',0.466,'kg/kg',0.99,'src-chebi',NULL,NULL)`,
  `INSERT OR IGNORE INTO facilities VALUES
    ('plant-cherkasy','chemical_plant','constrained',49.4444,32.0598,1200,840,'t NH3/day',0.70),
    ('line-ammonia-1','ammonia_line','active',49.4444,32.0598,1200,840,'t NH3/day',0.70)`,
  `INSERT OR IGNORE INTO capabilities VALUES
    ('cap-ammonia-1','line-ammonia-1','produce','nh3',1200,840,'t/day',0.72,'capability-v0.1')`,
  `INSERT OR IGNORE INTO dependencies VALUES
    ('dep-gas','cap-ammonia-1','network-gas','feedstock_energy',28,'GJ/t',0.74,1.0,7),
    ('dep-grid','cap-ammonia-1','network-grid','electricity',0.7,'MWh/t',0.88,0.82,2),
    ('dep-rail','cap-ammonia-1','network-rail','outbound_logistics',840,'t/day',0.67,0.76,4),
    ('dep-workforce','cap-ammonia-1','workforce-ammonia','required_skills',18,'qualified staff/shift',0.91,0.70,14)`,
  `INSERT OR IGNORE INTO observations VALUES
    ('obs-iea-energy','nh3','reference_energy_intensity',41,'GJ/t','observed','reported','2021-01-01','2026-07-29','src-iea',28,46),
    ('obs-line-capacity','line-ammonia-1','available_capacity',840,'t/day','estimated','modelled','2026-07-29','2026-07-29','src-orb',720,960),
    ('obs-demand','country-ua','annual_nitrogen_demand_index',100,'index','estimated','modelled','2026-07-29','2026-07-29','src-orb',88,115)`,
  `INSERT OR IGNORE INTO events VALUES
    ('evt-ammonia-001','transformation','Синтез аммиака — демонстрационная смена','observed','reconciled','2026-07-28T08:00:00Z','2026-07-28T16:00:00Z','plant-cherkasy','company-azot','haber-bosch-v0.1')`,
  `INSERT OR IGNORE INTO postings VALUES
    ('post-n2-in','evt-ammonia-001','n2','feedstock','out',164.7,'t','chemical','src-orb'),
    ('post-h2-in','evt-ammonia-001','h2','feedstock','out',35.3,'t','chemical','src-orb'),
    ('post-nh3-out','evt-ammonia-001','nh3','product','in',200,'t','chemical','src-orb'),
    ('post-energy-in','evt-ammonia-001','network-gas','energy_input','out',8200,'GJ','object','src-iea')`,
  `INSERT OR IGNORE INTO scenarios VALUES
    ('scenario-base','Базовый','Текущая доступность инфраструктуры и персонала','2027',0.74,0.88,0.67,0.91,0.03,0.55,'nitrogen-network-v0.1'),
    ('scenario-resilient','Устойчивый контур','Резервирование газа и железнодорожной логистики','2027',0.92,0.94,0.88,0.95,0.03,0.25,'nitrogen-network-v0.1'),
    ('scenario-stress','Логистический стресс','Ограничение газа и исходящей логистики','2027',0.48,0.79,0.42,0.86,0.03,0.20,'nitrogen-network-v0.1')`,
  `INSERT OR IGNORE INTO model_runs VALUES
    ('run-base','scenario-base','2026-07-29T00:00:00Z','nitrogen-network-v0.1',294000,246000,341000,'t NH3/year',0.67,'Железнодорожная сеть'),
    ('run-resilient','scenario-resilient','2026-07-29T00:00:00Z','nitrogen-network-v0.1',385000,351000,411000,'t NH3/year',0.81,'Газоснабжение'),
    ('run-stress','scenario-stress','2026-07-29T00:00:00Z','nitrogen-network-v0.1',184000,126000,229000,'t NH3/year',0.52,'Железнодорожная сеть')`,
  `INSERT OR IGNORE INTO process_models VALUES
    ('process-ammonia-1t','Синтез и доставка одной тонны аммиака','produce_and_deliver','line-ammonia-1','ammonia-circuit-v0.2',18,0.985,'2026-07-29','src-orb')`,
  `INSERT OR IGNORE INTO process_flows VALUES
    ('flow-n2','process-ammonia-1t','n2','input','feedstock',0.823529,'kg/kg NH3',0.005),
    ('flow-h2','process-ammonia-1t','h2','input','feedstock',0.176471,'kg/kg NH3',0.008),
    ('flow-gas','process-ammonia-1t','network-gas','input','feedstock_energy',0.028,'GJ/kg NH3',0.12),
    ('flow-grid','process-ammonia-1t','network-grid','input','electricity',0.0007,'MWh/kg NH3',0.08),
    ('flow-water','process-ammonia-1t','network-water','input','process_water',1.58,'kg/kg NH3',0.10),
    ('flow-nh3','process-ammonia-1t','nh3','output','product',1,'kg/kg NH3',0.015)`,
  `INSERT OR IGNORE INTO inventory_lots VALUES
    ('lot-nh3-001','nh3','tank-ammonia-1','company-azot',1000,'kg','planned','2026-07-29T08:00:00Z','src-orb')`,
  `INSERT OR IGNORE INTO transport_routes VALUES
    ('route-cherkasy-poltava','plant-cherkasy','warehouse-poltava','rail',286,60,'t/day',8,0.90,0.001,24),
    ('route-cherkasy-poltava-road','plant-cherkasy','warehouse-poltava','road',312,18,'t/day',6.5,0.86,0.002,8)`,
  `INSERT OR IGNORE INTO circuit_runs VALUES
    ('circuit-base-001','scenario-stress','ammonia-circuit-v0.2',1000,420,374,466,'kg NH3','logistics',0.637,42.9,0,'2026-07-29T12:00:00Z')`,
  `INSERT OR IGNORE INTO interventions VALUES
    ('intervention-road-001','circuit-base-001','Перенаправить партию через автомобильный терминал','route-cherkasy-poltava-road',12,440,'kg NH3','recommended','Автомобильный маршрут восстанавливает доступность доставки с 42% до 86%')`,
  `INSERT OR IGNORE INTO technologies VALUES
    ('tech-combustion','Спалювання палива','energy_conversion','chemical_energy','thermal_energy',0.90,'Тепло робочого тіла','Димові гази та розсіяне тепло','power-circuit-v0.1'),
    ('tech-steam-turbine','Парова турбіна','energy_conversion','thermal_energy','mechanical_rotation',0.40,'Обертання вала','Низькопотенційне тепло','power-circuit-v0.1'),
    ('tech-generator','Синхронний генератор','energy_conversion','mechanical_rotation','electric_potential',0.98,'Електричний потенціал','Нагрів обмоток і тертя','power-circuit-v0.1'),
    ('tech-step-up','Підвищувальний трансформатор','voltage_conversion','electric_potential_lv','electric_potential_hv',0.985,'Висока напруга','Тепло в осерді й обмотках','power-circuit-v0.1'),
    ('tech-hv-line','Магістральна ЛЕП','energy_transfer','electric_potential_hv','electric_potential_hv',0.96,'Переданий потенціал','Джоулеве тепло та коронні втрати','power-circuit-v0.1'),
    ('tech-substation','Приймальна підстанція','voltage_conversion','electric_potential_hv','electric_potential_mv',0.985,'Потенціал середньої напруги','Тепло й власні потреби','power-circuit-v0.1'),
    ('tech-mv-grid','Мережа середньої напруги','energy_transfer','electric_potential_mv','electric_potential_mv',0.95,'Розподілений потенціал','Джоулеве тепло','power-circuit-v0.1'),
    ('tech-distribution-transformer','Розподільчий трансформатор','voltage_conversion','electric_potential_mv','electric_potential_lv',0.98,'Потенціал 0,4 кВ','Тепло в осерді й обмотках','power-circuit-v0.1'),
    ('tech-lv-grid','Низьковольтна мережа','energy_transfer','electric_potential_lv','electric_potential_socket',0.96,'Потенціал у розетці','Джоулеве тепло','power-circuit-v0.1'),
    ('tech-refrigeration','Компресійний холодильний цикл','temperature_control','electric_potential','temperature_gradient',3.0,'Відведення тепла з холодильної камери','Тепло в приміщення','power-circuit-v0.1'),
    ('tech-led','Світлодіодна електролюмінесценція','radiation_conversion','electric_potential','electromagnetic_waves',0.35,'Видиме електромагнітне випромінювання','Тепло','power-circuit-v0.1')`,
  `INSERT OR IGNORE INTO principle_systems VALUES
    ('system-thermal-power-plant','Теплова електростанція','generation','Прийняти паливо та створити електричний потенціал','fuel','electric_potential', 'power-circuit-v0.1'),
    ('system-transmission-grid','Система передачі','transmission','Підвищити напругу і передати потенціал на відстань','electric_potential_lv','electric_potential_hv','power-circuit-v0.1'),
    ('system-distribution-grid','Система розподілу','distribution','Знизити напругу та доставити потенціал споживачу','electric_potential_hv','electric_potential_socket','power-circuit-v0.1')`,
  `INSERT OR IGNORE INTO end_products VALUES
    ('product-fridge','Холодильник','civil_appliance',0.15,'Електричний потенціал → робота компресора → градієнт температури','Відведене тепло з камери','Електроенергія та відведене тепло у приміщенні',3.0),
    ('product-led','LED-лампа','civil_appliance',0.01,'Електричний потенціал → електромагнітні хвилі + тепло','Видиме випромінювання','Тепло',0.35)`,
  `INSERT OR IGNORE INTO test_models VALUES
    ('test-power-home-001','ТЕС → будинок: холодильник + LED','Одногодинний тест сумісної роботи генерації, мережі та двох кінцевих виробів','active',1,'power-circuit-v0.1')`,
  `INSERT OR IGNORE INTO test_model_components VALUES
    ('tmc-01','test-power-home-001','principle_system','system-thermal-power-plant',1,'main',1),
    ('tmc-02','test-power-home-001','technology','tech-step-up',2,'main',1),
    ('tmc-03','test-power-home-001','technology','tech-hv-line',3,'main',1),
    ('tmc-04','test-power-home-001','technology','tech-substation',4,'main',1),
    ('tmc-05','test-power-home-001','technology','tech-mv-grid',5,'main',1),
    ('tmc-06','test-power-home-001','technology','tech-distribution-transformer',6,'civil',1),
    ('tmc-07','test-power-home-001','technology','tech-lv-grid',7,'civil',1),
    ('tmc-08','test-power-home-001','end_product','product-fridge',8,'civil',100),
    ('tmc-09','test-power-home-001','end_product','product-led',9,'civil',1000)`,
  `INSERT OR IGNORE INTO territorial_units VALUES
    ('territory-moscow-demo','Москва','abstract_metropolitan_area','RU',55.7558,37.6176,'approximate_centroid',13000000,0.15,'modelled_demo','src-orb')`,
  `INSERT OR IGNORE INTO real_systems VALUES
    ('real-grid-moscow-demo','Агрегований енергетичний вузол Москви','distribution_region','system-distribution-grid',55.7558,37.6176,25000,'territory-moscow-demo','modelled_demo','planned','src-orb')`,
];

async function ensureDatabase() {
  const db = env.DB;
  if (!db) throw new Error("D1 binding DB is unavailable");
  await db.batch(schemaStatements.map((statement) => db.prepare(statement)));
  for (const statement of seedStatements) {
    await db.prepare(statement).run();
  }
  return db;
}

async function all(db: D1Database, sql: string): Promise<Row[]> {
  const result = await db.prepare(sql).all<Row>();
  return result.results;
}

export type WorldSnapshot = Awaited<ReturnType<typeof getWorldSnapshot>>;

export async function getWorldSnapshot() {
  const db = await ensureDatabase();
  const [entities, relations, facilities, capabilities, dependencies, events, postings, scenarios, runs, sources, externalIdentities, processModels, processFlows, inventoryLots, transportRoutes, circuitRuns, interventions, technologies, principleSystems, endProducts, testModels, testModelComponents, territorialUnits, realSystems] =
    await Promise.all([
      all(db, "SELECT * FROM entities ORDER BY level, name"),
      all(db, "SELECT * FROM relations ORDER BY predicate"),
      all(db, "SELECT * FROM facilities ORDER BY entity_id"),
      all(db, "SELECT * FROM capabilities ORDER BY id"),
      all(db, `SELECT d.*, e.name AS dependency_name
        FROM dependencies d JOIN entities e ON e.id = d.dependency_entity_id
        ORDER BY d.criticality DESC`),
      all(db, "SELECT * FROM events ORDER BY started_at DESC"),
      all(db, `SELECT p.*, e.name AS entity_name, e.symbol
        FROM postings p JOIN entities e ON e.id = p.entity_id ORDER BY p.id`),
      all(db, "SELECT * FROM scenarios ORDER BY probability DESC"),
      all(db, "SELECT * FROM model_runs ORDER BY expected_output DESC"),
      all(db, "SELECT * FROM sources ORDER BY name"),
      all(db, "SELECT * FROM external_identities ORDER BY namespace"),
      all(db, "SELECT * FROM process_models ORDER BY id"),
      all(db, `SELECT f.*, e.name AS entity_name, e.symbol
        FROM process_flows f JOIN entities e ON e.id = f.entity_id ORDER BY f.direction, f.id`),
      all(db, `SELECT l.*, e.name AS entity_name, c.name AS container_name
        FROM inventory_lots l
        JOIN entities e ON e.id = l.entity_id
        JOIN entities c ON c.id = l.container_entity_id ORDER BY l.observed_at DESC`),
      all(db, `SELECT r.*, o.name AS origin_name, d.name AS destination_name
        FROM transport_routes r
        JOIN entities o ON o.id = r.origin_entity_id
        JOIN entities d ON d.id = r.destination_entity_id ORDER BY r.duration_hours`),
      all(db, "SELECT * FROM circuit_runs ORDER BY run_at DESC"),
      all(db, "SELECT * FROM interventions ORDER BY id"),
      all(db, "SELECT * FROM technologies ORDER BY category, name"),
      all(db, "SELECT * FROM principle_systems ORDER BY system_type, name"),
      all(db, "SELECT * FROM end_products ORDER BY product_type, name"),
      all(db, "SELECT * FROM test_models ORDER BY name"),
      all(db, "SELECT * FROM test_model_components ORDER BY test_model_id, sequence_no"),
      all(db, "SELECT * FROM territorial_units ORDER BY name"),
      all(db, "SELECT * FROM real_systems ORDER BY name"),
    ]);

  return {
    generatedAt: new Date().toISOString(),
    entities,
    relations,
    facilities,
    capabilities,
    dependencies,
    events,
    postings,
    scenarios,
    runs,
    sources,
    externalIdentities,
    processModels,
    processFlows,
    inventoryLots,
    transportRoutes,
    circuitRuns,
    interventions,
    technologies,
    principleSystems,
    endProducts,
    testModels,
    testModelComponents,
    territorialUnits,
    realSystems,
  };
}
