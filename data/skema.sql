-- --------------------------------------------------------
-- Host:                         127.0.0.1
-- Versi server:                 8.0.30 - MySQL Community Server - GPL
-- OS Server:                    Win64
-- HeidiSQL Versi:               12.14.0.7165
-- --------------------------------------------------------

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET NAMES utf8 */;
/*!50503 SET NAMES utf8mb4 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;

-- membuang struktur untuk table asetpedia.airports
CREATE TABLE IF NOT EXISTS `airports` (
  `id` int NOT NULL,
  `ident` varchar(20) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `type` varchar(50) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `name` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `latitude_deg` double DEFAULT NULL,
  `longitude_deg` double DEFAULT NULL,
  `elevation_ft` int DEFAULT NULL,
  `continent` varchar(10) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `iso_country` varchar(10) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `iso_region` varchar(20) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `municipality` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `scheduled_service` varchar(10) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `icao_code` varchar(20) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `iata_code` varchar(20) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `gps_code` varchar(20) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `local_code` varchar(20) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `home_link` text COLLATE utf8mb4_general_ci,
  `wikipedia_link` text COLLATE utf8mb4_general_ci,
  `keywords` text COLLATE utf8mb4_general_ci,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Pengeluaran data tidak dipilih.

-- membuang struktur untuk table asetpedia.ais_history
CREATE TABLE IF NOT EXISTS `ais_history` (
  `id` int NOT NULL AUTO_INCREMENT,
  `mmsi` varchar(20) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `name` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `type` varchar(100) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `lat` decimal(12,8) DEFAULT NULL,
  `lon` decimal(12,8) DEFAULT NULL,
  `speed` float DEFAULT NULL,
  `heading` float DEFAULT NULL,
  `status` varchar(100) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `destination` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `timestamp` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `mmsi` (`mmsi`),
  KEY `timestamp` (`timestamp`)
) ENGINE=InnoDB AUTO_INCREMENT=2389 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Pengeluaran data tidak dipilih.

-- membuang struktur untuk table asetpedia.article
CREATE TABLE IF NOT EXISTS `article` (
  `id` varchar(191) COLLATE utf8mb4_unicode_ci NOT NULL,
  `title` varchar(1000) COLLATE utf8mb4_unicode_ci NOT NULL,
  `description` text COLLATE utf8mb4_unicode_ci,
  `content` longtext COLLATE utf8mb4_unicode_ci,
  `link` varchar(768) COLLATE utf8mb4_unicode_ci NOT NULL,
  `pubDate` datetime(3) DEFAULT NULL,
  `imageUrl` text COLLATE utf8mb4_unicode_ci,
  `author` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `sourceId` varchar(191) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `sourceName` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `category` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `sentiment` varchar(50) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `sentimentScore` float DEFAULT NULL,
  `sentiment_lang` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  `impactScore` float DEFAULT NULL,
  `embedding` longblob,
  `keywords` text COLLATE utf8mb4_unicode_ci,
  `entities` text COLLATE utf8mb4_unicode_ci,
  `summary` text COLLATE utf8mb4_unicode_ci,
  `createdAt` datetime(3) DEFAULT CURRENT_TIMESTAMP(3),
  `updatedAt` datetime(3) DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  PRIMARY KEY (`id`),
  UNIQUE KEY `link` (`link`),
  KEY `pubDate` (`pubDate`),
  KEY `sourceName` (`sourceName`),
  KEY `sentiment` (`sentiment`),
  KEY `sourceId` (`sourceId`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Pengeluaran data tidak dipilih.

-- membuang struktur untuk table asetpedia.countries
CREATE TABLE IF NOT EXISTS `countries` (
  `id` int NOT NULL,
  `code` varchar(10) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL,
  `name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL,
  `continent` varchar(10) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL,
  `wikipedia_link` text,
  `keywords` text,
  `lat` decimal(10,6) DEFAULT NULL,
  `lon` decimal(10,6) DEFAULT NULL,
  `airport_count` int DEFAULT '0',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- Pengeluaran data tidak dipilih.

-- membuang struktur untuk table asetpedia.country_codes
CREATE TABLE IF NOT EXISTS `country_codes` (
  `country_code` text COLLATE utf8mb4_unicode_ci,
  `country_name` text COLLATE utf8mb4_unicode_ci
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Pengeluaran data tidak dipilih.

-- membuang struktur untuk table asetpedia.country_codes_old
CREATE TABLE IF NOT EXISTS `country_codes_old` (
  `country_code` text COLLATE utf8mb4_unicode_ci,
  `country_name` text COLLATE utf8mb4_unicode_ci
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Pengeluaran data tidak dipilih.

-- membuang struktur untuk table asetpedia.datacenter_hub
CREATE TABLE IF NOT EXISTS `datacenter_hub` (
  `id` int NOT NULL AUTO_INCREMENT,
  `facility_name` varchar(255) DEFAULT NULL,
  `company_name` varchar(255) DEFAULT NULL,
  `street_address` text,
  `city_name` varchar(100) DEFAULT NULL,
  `zip_code` varchar(50) DEFAULT NULL,
  `country_name` varchar(100) DEFAULT NULL,
  `full_address` text,
  `latitude` double DEFAULT NULL,
  `longitude` double DEFAULT NULL,
  `is_approximate` tinyint(1) DEFAULT '0',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=25758 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- Pengeluaran data tidak dipilih.

-- membuang struktur untuk table asetpedia.datacenter_stats
CREATE TABLE IF NOT EXISTS `datacenter_stats` (
  `country` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `total_data_centers` int DEFAULT '0',
  `hyperscale_data_centers` int DEFAULT '0',
  `colocation_data_centers` int DEFAULT '0',
  `floor_space_sqft_total` text COLLATE utf8mb4_unicode_ci,
  `power_capacity_MW_total` text COLLATE utf8mb4_unicode_ci,
  `average_renewable_energy_usage_percent` text COLLATE utf8mb4_unicode_ci,
  `tier_distribution` text COLLATE utf8mb4_unicode_ci,
  `key_operators` text COLLATE utf8mb4_unicode_ci,
  `cloud_provider` text COLLATE utf8mb4_unicode_ci,
  `internet_penetration_percent` text COLLATE utf8mb4_unicode_ci,
  `avg_latency_to_global_hubs_ms` text COLLATE utf8mb4_unicode_ci,
  `number_of_fiber_connections` int DEFAULT '0',
  `growth_rate_of_data_centers_percent_per_year` decimal(5,2) DEFAULT '0.00',
  `cooling_technologies_common` text COLLATE utf8mb4_unicode_ci,
  `regulatory_challenges_or_limits` text COLLATE utf8mb4_unicode_ci,
  `disaster_recovery_sites_common` text COLLATE utf8mb4_unicode_ci,
  `green_dc_initiatives_description` text COLLATE utf8mb4_unicode_ci,
  `source_of_data` text COLLATE utf8mb4_unicode_ci,
  PRIMARY KEY (`country`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Pengeluaran data tidak dipilih.

-- membuang struktur untuk table asetpedia.dc_addresses
CREATE TABLE IF NOT EXISTS `dc_addresses` (
  `osm_id` bigint NOT NULL,
  `country` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `city` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `street` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `housenumber` varchar(100) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `postcode` varchar(100) COLLATE utf8mb4_general_ci DEFAULT NULL,
  PRIMARY KEY (`osm_id`),
  KEY `country` (`country`),
  KEY `city` (`city`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Pengeluaran data tidak dipilih.

-- membuang struktur untuk table asetpedia.dc_contact
CREATE TABLE IF NOT EXISTS `dc_contact` (
  `osm_id` bigint NOT NULL,
  `website` varchar(500) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `phone` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `email` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL,
  PRIMARY KEY (`osm_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Pengeluaran data tidak dipilih.

-- membuang struktur untuk table asetpedia.dc_meta
CREATE TABLE IF NOT EXISTS `dc_meta` (
  `id` int NOT NULL AUTO_INCREMENT,
  `osm_id` bigint DEFAULT NULL,
  `meta_key` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `meta_value` text COLLATE utf8mb4_general_ci,
  PRIMARY KEY (`id`),
  KEY `osm_id` (`osm_id`),
  KEY `meta_key` (`meta_key`)
) ENGINE=InnoDB AUTO_INCREMENT=1194 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Pengeluaran data tidak dipilih.

-- membuang struktur untuk table asetpedia.dc_nodes
CREATE TABLE IF NOT EXISTS `dc_nodes` (
  `osm_id` bigint NOT NULL,
  `lat` decimal(11,8) DEFAULT NULL,
  `lng` decimal(11,8) DEFAULT NULL,
  `name` varchar(500) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `operator` varchar(500) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `raw_tags` json DEFAULT NULL,
  PRIMARY KEY (`osm_id`),
  KEY `name` (`name`),
  KEY `operator` (`operator`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Pengeluaran data tidak dipilih.

-- membuang struktur untuk table asetpedia.depth_code_lut
CREATE TABLE IF NOT EXISTS `depth_code_lut` (
  `depth_code` text COLLATE utf8mb4_unicode_ci,
  `feet` text COLLATE utf8mb4_unicode_ci,
  `meters` text COLLATE utf8mb4_unicode_ci
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Pengeluaran data tidak dipilih.

-- membuang struktur untuk table asetpedia.drydock_marine_railway_code_lut
CREATE TABLE IF NOT EXISTS `drydock_marine_railway_code_lut` (
  `drydock_marine_railway_code` text COLLATE utf8mb4_unicode_ci,
  `drydock_marine_railway_code_description` text COLLATE utf8mb4_unicode_ci
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Pengeluaran data tidak dipilih.

-- membuang struktur untuk table asetpedia.feedsource
CREATE TABLE IF NOT EXISTS `feedsource` (
  `id_number` int NOT NULL AUTO_INCREMENT,
  `id` text COLLATE utf8mb4_unicode_ci NOT NULL,
  `name` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `url` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `type` varchar(50) COLLATE utf8mb4_unicode_ci DEFAULT 'rss',
  `category` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `lastFetch` datetime(3) DEFAULT NULL,
  `active` tinyint(1) DEFAULT '1',
  `priority` int DEFAULT '0',
  PRIMARY KEY (`id_number`) USING BTREE,
  UNIQUE KEY `url` (`url`)
) ENGINE=InnoDB AUTO_INCREMENT=992 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Pengeluaran data tidak dipilih.

-- membuang struktur untuk table asetpedia.global_conflicts
CREATE TABLE IF NOT EXISTS `global_conflicts` (
  `id` int NOT NULL AUTO_INCREMENT,
  `negara` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `detail_wilayah` text COLLATE utf8mb4_general_ci,
  `latitude` decimal(10,6) DEFAULT NULL,
  `longitude` decimal(10,6) DEFAULT NULL,
  `detail_konflik` text COLLATE utf8mb4_general_ci,
  `penjelasan_singkat` text COLLATE utf8mb4_general_ci,
  `daftar_pihak_terlibat` text COLLATE utf8mb4_general_ci,
  `jumlah_korban_meninggal` text COLLATE utf8mb4_general_ci,
  `jumlah_korban_luka` text COLLATE utf8mb4_general_ci,
  `kerusakan_infrastruktur` text COLLATE utf8mb4_general_ci,
  `kerusakan_rumah` text COLLATE utf8mb4_general_ci,
  `situasi_saat_ini` text COLLATE utf8mb4_general_ci,
  `index_keparahan` int DEFAULT NULL,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=53 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Pengeluaran data tidak dipilih.

-- membuang struktur untuk table asetpedia.global_trade_alerts
CREATE TABLE IF NOT EXISTS `global_trade_alerts` (
  `id` int NOT NULL AUTO_INCREMENT,
  `intervention_id` int NOT NULL,
  `title` text COLLATE utf8mb4_unicode_ci NOT NULL,
  `announcement_date` date DEFAULT NULL,
  `implementation_date` date DEFAULT NULL,
  `removal_date` date DEFAULT NULL,
  `implementing_jurisdiction` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `affected_jurisdictions` text COLLATE utf8mb4_unicode_ci,
  `type` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `status` varchar(50) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `description` text COLLATE utf8mb4_unicode_ci,
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_intervention` (`intervention_id`),
  KEY `announcement_date` (`announcement_date`),
  KEY `implementing_jurisdiction` (`implementing_jurisdiction`)
) ENGINE=InnoDB AUTO_INCREMENT=1301 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Pengeluaran data tidak dipilih.

-- membuang struktur untuk table asetpedia.government_facilities
CREATE TABLE IF NOT EXISTS `government_facilities` (
  `id` int NOT NULL AUTO_INCREMENT,
  `operator` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `operatorQID` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `jurisdictions` text COLLATE utf8mb4_general_ci,
  `jurisdictionQIDs` text COLLATE utf8mb4_general_ci,
  `country` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `countryQID` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `city` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `cityQID` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `address` text COLLATE utf8mb4_general_ci,
  `latitude` decimal(10,8) DEFAULT NULL,
  `longitude` decimal(11,8) DEFAULT NULL,
  `phone` text COLLATE utf8mb4_general_ci,
  `email` text COLLATE utf8mb4_general_ci,
  `website` text COLLATE utf8mb4_general_ci,
  `facebook` text COLLATE utf8mb4_general_ci,
  `twitter` text COLLATE utf8mb4_general_ci,
  `youtube` text COLLATE utf8mb4_general_ci,
  `picture` text COLLATE utf8mb4_general_ci,
  `pictureAuthor` text COLLATE utf8mb4_general_ci,
  `pictureLicense` text COLLATE utf8mb4_general_ci,
  `pictureLicenseURL` text COLLATE utf8mb4_general_ci,
  `facility_type` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `typeQID` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `creation` text COLLATE utf8mb4_general_ci,
  `qid` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=10458 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Pengeluaran data tidak dipilih.

-- membuang struktur untuk table asetpedia.harbor_size_lut
CREATE TABLE IF NOT EXISTS `harbor_size_lut` (
  `harbor_size_code` text COLLATE utf8mb4_unicode_ci,
  `harbor_size` text COLLATE utf8mb4_unicode_ci
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Pengeluaran data tidak dipilih.

-- membuang struktur untuk table asetpedia.harbor_type_lut
CREATE TABLE IF NOT EXISTS `harbor_type_lut` (
  `harbor_type_code` text COLLATE utf8mb4_unicode_ci,
  `harbor_type_description` text COLLATE utf8mb4_unicode_ci
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Pengeluaran data tidak dipilih.

-- membuang struktur untuk table asetpedia.high_priority_datacenters
CREATE TABLE IF NOT EXISTS `high_priority_datacenters` (
  `id` int NOT NULL AUTO_INCREMENT,
  `dc_id` varchar(50) DEFAULT NULL,
  `operator_name` varchar(255) DEFAULT NULL,
  `facility_name` varchar(255) DEFAULT NULL,
  `operational_status` varchar(50) DEFAULT NULL,
  `year_opened` varchar(20) DEFAULT NULL,
  `street_address` text,
  `city` varchar(100) DEFAULT NULL,
  `state_province` varchar(100) DEFAULT NULL,
  `country_code` varchar(10) DEFAULT NULL,
  `postal_code` varchar(50) DEFAULT NULL,
  `latitude` varchar(50) DEFAULT NULL,
  `longitude` varchar(50) DEFAULT NULL,
  `it_load_mw` varchar(50) DEFAULT NULL,
  `total_building_size` varchar(100) DEFAULT NULL,
  `white_space_size` varchar(100) DEFAULT NULL,
  `rack_capacity` varchar(100) DEFAULT NULL,
  `tier_level` varchar(50) DEFAULT NULL,
  `floor_loading_cap` varchar(100) DEFAULT NULL,
  `power_redundancy` varchar(100) DEFAULT NULL,
  `pue_design` varchar(50) DEFAULT NULL,
  `cooling_type` varchar(100) DEFAULT NULL,
  `renewable_energy_pct` varchar(50) DEFAULT NULL,
  `carrier_neutral` varchar(10) DEFAULT NULL,
  `total_carriers` varchar(50) DEFAULT NULL,
  `ix_presence` text,
  `fiber_entry_points` varchar(50) DEFAULT NULL,
  `data_source` varchar(255) DEFAULT NULL,
  `last_updated` date DEFAULT NULL,
  `notes` text,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=351 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- Pengeluaran data tidak dipilih.

-- membuang struktur untuk table asetpedia.idx_entity
CREATE TABLE IF NOT EXISTS `idx_entity` (
  `kode` varchar(10) COLLATE utf8mb4_unicode_ci NOT NULL,
  `nama_perusahaan` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `sektor` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `sub_sektor` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `industri` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `sub_industri` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `tgl_pencatatan` date DEFAULT NULL,
  `papan` varchar(50) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `website` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `email` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `alamat` text COLLATE utf8mb4_unicode_ci,
  PRIMARY KEY (`kode`),
  KEY `nama_perusahaan` (`nama_perusahaan`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Pengeluaran data tidak dipilih.

-- membuang struktur untuk table asetpedia.industrial_zone_poi
CREATE TABLE IF NOT EXISTS `industrial_zone_poi` (
  `hub_id` int NOT NULL,
  `facility_scan` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci,
  `last_updated` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`hub_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Pengeluaran data tidak dipilih.

-- membuang struktur untuk table asetpedia.industrial_zones
CREATE TABLE IF NOT EXISTS `industrial_zones` (
  `id` int NOT NULL,
  `name` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `latitude` decimal(11,8) DEFAULT NULL,
  `longitude` decimal(11,8) DEFAULT NULL,
  `country` varchar(100) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `sector` text COLLATE utf8mb4_general_ci,
  `ownership` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `region_1` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `region_2` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `region_3` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Pengeluaran data tidak dipilih.

-- membuang struktur untuk table asetpedia.isps
CREATE TABLE IF NOT EXISTS `isps` (
  `id` int NOT NULL AUTO_INCREMENT,
  `name` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `country` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `website` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `details` text COLLATE utf8mb4_unicode_ci,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_isp_country` (`name`,`country`),
  KEY `country` (`country`),
  KEY `name` (`name`)
) ENGINE=InnoDB AUTO_INCREMENT=597 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Pengeluaran data tidak dipilih.

-- membuang struktur untuk table asetpedia.lng_facilities
CREATE TABLE IF NOT EXISTS `lng_facilities` (
  `id` int NOT NULL AUTO_INCREMENT,
  `fac_name` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `operator` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `country` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `latitude` decimal(10,8) DEFAULT NULL,
  `longitude` decimal(11,8) DEFAULT NULL,
  `liq_capacity_bpd` double DEFAULT NULL,
  `fac_status` varchar(100) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `fac_type` varchar(100) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `commodity` varchar(100) COLLATE utf8mb4_general_ci DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=548 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Pengeluaran data tidak dipilih.

-- membuang struktur untuk table asetpedia.maximum_size_vessel_lut
CREATE TABLE IF NOT EXISTS `maximum_size_vessel_lut` (
  `maximum_size_vessel_code` text COLLATE utf8mb4_unicode_ci,
  `maximum_size_vessel_description` text COLLATE utf8mb4_unicode_ci
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Pengeluaran data tidak dipilih.

-- membuang struktur untuk table asetpedia.military_facilities
CREATE TABLE IF NOT EXISTS `military_facilities` (
  `id` int NOT NULL AUTO_INCREMENT,
  `country` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `name` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `city` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `latitude` decimal(10,8) DEFAULT NULL,
  `longitude` decimal(11,8) DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=127 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Pengeluaran data tidak dipilih.

-- membuang struktur untuk table asetpedia.military_strength
CREATE TABLE IF NOT EXISTS `military_strength` (
  `country` varchar(255) COLLATE utf8mb4_general_ci NOT NULL,
  `gfp_rank` int DEFAULT NULL,
  `power_index` float DEFAULT NULL,
  `active_personnel` bigint DEFAULT NULL,
  `reserve_personnel` bigint DEFAULT NULL,
  `paramilitary` bigint DEFAULT NULL,
  `total_personnel` bigint DEFAULT NULL,
  `tanks` int DEFAULT NULL,
  `armored_vehicles` int DEFAULT NULL,
  `artillery_self_propelled` int DEFAULT NULL,
  `mlrs_rocket_projectors` int DEFAULT NULL,
  `total_aircraft` int DEFAULT NULL,
  `fighter_interceptors` int DEFAULT NULL,
  `attack_aircraft` int DEFAULT NULL,
  `helicopters` int DEFAULT NULL,
  `attack_helicopters` int DEFAULT NULL,
  `transport_aircraft` int DEFAULT NULL,
  `trainer_aircraft` int DEFAULT NULL,
  `total_naval_vessels` int DEFAULT NULL,
  `aircraft_carriers` int DEFAULT NULL,
  `helicopter_carriers` int DEFAULT NULL,
  `submarines` int DEFAULT NULL,
  `destroyers` int DEFAULT NULL,
  `frigates` int DEFAULT NULL,
  `corvettes` int DEFAULT NULL,
  `patrol_vessels` int DEFAULT NULL,
  `defense_budget_usd` bigint DEFAULT NULL,
  PRIMARY KEY (`country`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Pengeluaran data tidak dipilih.

-- membuang struktur untuk table asetpedia.mines_data
CREATE TABLE IF NOT EXISTS `mines_data` (
  `id` int NOT NULL AUTO_INCREMENT,
  `site_name` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `country` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `state_province` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `county` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `latitude` decimal(11,8) DEFAULT NULL,
  `longitude` decimal(11,8) DEFAULT NULL,
  `commod1` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `commod2` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `commod3` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `dev_stat` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `region` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `oper_type` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `prod_size` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `com_type` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `cur_owner` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `score` varchar(10) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `country` (`country`),
  KEY `commod1` (`commod1`),
  KEY `dev_stat` (`dev_stat`)
) ENGINE=InnoDB AUTO_INCREMENT=24130 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Pengeluaran data tidak dipilih.

-- membuang struktur untuk table asetpedia.offshore_platforms
CREATE TABLE IF NOT EXISTS `offshore_platforms` (
  `id` int NOT NULL AUTO_INCREMENT,
  `ogim_id` int DEFAULT NULL,
  `category` varchar(100) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `region` varchar(100) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `country` varchar(100) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `state_prov` varchar(100) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `src_ref_id` varchar(100) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `src_date` varchar(50) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `on_offshore` varchar(50) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `fac_name` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `fac_id` varchar(100) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `fac_type` varchar(100) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `fac_status` varchar(100) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `ogim_status` varchar(100) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `operator` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `install_date` varchar(50) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `commodity` varchar(100) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `latitude` decimal(10,8) DEFAULT NULL,
  `longitude` decimal(11,8) DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `country` (`country`),
  KEY `fac_name` (`fac_name`)
) ENGINE=InnoDB AUTO_INCREMENT=3904 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Pengeluaran data tidak dipilih.

-- membuang struktur untuk table asetpedia.oil_refineries
CREATE TABLE IF NOT EXISTS `oil_refineries` (
  `id` int NOT NULL,
  `nama_kilang` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `negara` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `provinsi_atau_negara_bagian` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `latitude` decimal(12,8) DEFAULT NULL,
  `longitude` decimal(12,8) DEFAULT NULL,
  `kapasitas_bbl_per_hari` decimal(20,2) DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_negara` (`negara`),
  KEY `idx_nama` (`nama_kilang`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Pengeluaran data tidak dipilih.

-- membuang struktur untuk table asetpedia.oil_trade_countries
CREATE TABLE IF NOT EXISTS `oil_trade_countries` (
  `origin_id` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `origin_name` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `iso3` varchar(10) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `lat` decimal(11,8) DEFAULT NULL,
  `lon` decimal(11,8) DEFAULT NULL,
  `region` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  PRIMARY KEY (`origin_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Pengeluaran data tidak dipilih.

-- membuang struktur untuk table asetpedia.oil_trades
CREATE TABLE IF NOT EXISTS `oil_trades` (
  `id` int NOT NULL AUTO_INCREMENT,
  `period` varchar(50) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `origin_id` varchar(50) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `origin_name` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `destination_id` varchar(50) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `destination_name` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `grade_id` varchar(50) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `grade_name` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `quantity` decimal(20,5) DEFAULT NULL,
  `frequency` varchar(50) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `unique_trade` (`period`,`origin_id`,`destination_id`,`grade_id`,`frequency`),
  KEY `period` (`period`),
  KEY `origin_id` (`origin_id`)
) ENGINE=InnoDB AUTO_INCREMENT=218007 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Pengeluaran data tidak dipilih.

-- membuang struktur untuk table asetpedia.police_facilities
CREATE TABLE IF NOT EXISTS `police_facilities` (
  `id` int NOT NULL AUTO_INCREMENT,
  `country` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `organization_name` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `hq_name` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `city` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `address` text COLLATE utf8mb4_general_ci,
  `latitude` decimal(10,8) DEFAULT NULL,
  `longitude` decimal(11,8) DEFAULT NULL,
  `website` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `notes` text COLLATE utf8mb4_general_ci,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=198 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Pengeluaran data tidak dipilih.

-- membuang struktur untuk table asetpedia.power_plants
CREATE TABLE IF NOT EXISTS `power_plants` (
  `id` int NOT NULL AUTO_INCREMENT,
  `country_long` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `name` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `capacity_mw` float DEFAULT NULL,
  `latitude` decimal(10,8) DEFAULT NULL,
  `longitude` decimal(11,8) DEFAULT NULL,
  `primary_fuel` varchar(100) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `commissioning_year` float DEFAULT NULL,
  `owner` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=34937 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Pengeluaran data tidak dipilih.

-- membuang struktur untuk table asetpedia.railway_stations
CREATE TABLE IF NOT EXISTS `railway_stations` (
  `id` int NOT NULL,
  `name` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `latitude` decimal(12,9) DEFAULT NULL,
  `longitude` decimal(12,9) DEFAULT NULL,
  `country_code` varchar(10) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `is_main_station` tinyint(1) DEFAULT '0',
  `is_airport` tinyint(1) DEFAULT '0',
  `time_zone` varchar(50) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `uic_ref` varchar(50) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `operator` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `platforms` int DEFAULT NULL,
  `website` text COLLATE utf8mb4_general_ci,
  `wikidata` varchar(50) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `wikipedia` text COLLATE utf8mb4_general_ci,
  `usage_type` varchar(50) COLLATE utf8mb4_general_ci DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_country` (`country_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Pengeluaran data tidak dipilih.

-- membuang struktur untuk table asetpedia.repairs_code_lut
CREATE TABLE IF NOT EXISTS `repairs_code_lut` (
  `repairs_code` text COLLATE utf8mb4_unicode_ci,
  `repairs_code_description` text COLLATE utf8mb4_unicode_ci
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Pengeluaran data tidak dipilih.

-- membuang struktur untuk table asetpedia.shelter_afforded_lut
CREATE TABLE IF NOT EXISTS `shelter_afforded_lut` (
  `shelter_afforded_code` text COLLATE utf8mb4_unicode_ci,
  `shelter_afforded_description` text COLLATE utf8mb4_unicode_ci
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Pengeluaran data tidak dipilih.

-- membuang struktur untuk table asetpedia.strategic_projects
CREATE TABLE IF NOT EXISTS `strategic_projects` (
  `id` int NOT NULL AUTO_INCREMENT,
  `project_no` int DEFAULT NULL,
  `name` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `country` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `region` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `category` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `sub_category` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `status` varchar(100) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `year_start` varchar(50) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `year_end` varchar(50) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `budget_usd` decimal(20,2) DEFAULT NULL,
  `latitude` decimal(10,8) DEFAULT NULL,
  `longitude` decimal(11,8) DEFAULT NULL,
  `location` text COLLATE utf8mb4_general_ci,
  `description` text COLLATE utf8mb4_general_ci,
  `impact` text COLLATE utf8mb4_general_ci,
  `jobs` varchar(100) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `funding_source` text COLLATE utf8mb4_general_ci,
  `notes` text COLLATE utf8mb4_general_ci,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=121 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Pengeluaran data tidak dipilih.

-- membuang struktur untuk table asetpedia.user_calendar_watchlist
CREATE TABLE IF NOT EXISTS `user_calendar_watchlist` (
  `id` int NOT NULL AUTO_INCREMENT,
  `symbol` varchar(50) COLLATE utf8mb4_general_ci NOT NULL,
  `name` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `added_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `symbol` (`symbol`)
) ENGINE=InnoDB AUTO_INCREMENT=4 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Pengeluaran data tidak dipilih.

-- membuang struktur untuk table asetpedia.wpi_data
CREATE TABLE IF NOT EXISTS `wpi_data` (
  `world_port_index_number` int DEFAULT NULL,
  `region_index` int DEFAULT NULL,
  `main_port_name` text COLLATE utf8mb4_unicode_ci,
  `wpi_country_code` text COLLATE utf8mb4_unicode_ci,
  `latitude_degrees` int DEFAULT NULL,
  `latitude_minutes` int DEFAULT NULL,
  `latitude_hemisphere` text COLLATE utf8mb4_unicode_ci,
  `longitude_degrees` int DEFAULT NULL,
  `longitude_minutes` int DEFAULT NULL,
  `longitude_hemisphere` text COLLATE utf8mb4_unicode_ci,
  `publication` text COLLATE utf8mb4_unicode_ci,
  `chart` text COLLATE utf8mb4_unicode_ci,
  `harbor_size_code` text COLLATE utf8mb4_unicode_ci,
  `harbor_type_code` text COLLATE utf8mb4_unicode_ci,
  `shelter_afforded_code` text COLLATE utf8mb4_unicode_ci,
  `entrance_restriction_tide` text COLLATE utf8mb4_unicode_ci,
  `entrance_restriction_swell` text COLLATE utf8mb4_unicode_ci,
  `entrance_restriction_ice` text COLLATE utf8mb4_unicode_ci,
  `entrance_restriction_other` text COLLATE utf8mb4_unicode_ci,
  `overhead_limits` text COLLATE utf8mb4_unicode_ci,
  `channel_depth` text COLLATE utf8mb4_unicode_ci,
  `anchorage_depth` text COLLATE utf8mb4_unicode_ci,
  `cargo_pier_depth` text COLLATE utf8mb4_unicode_ci,
  `oil_terminal_depth` text COLLATE utf8mb4_unicode_ci,
  `tide` text COLLATE utf8mb4_unicode_ci,
  `maxsize_vessel_code` text COLLATE utf8mb4_unicode_ci,
  `good_holding_ground` text COLLATE utf8mb4_unicode_ci,
  `turning_area` text COLLATE utf8mb4_unicode_ci,
  `first_port_of_entry` text COLLATE utf8mb4_unicode_ci,
  `us_representative` text COLLATE utf8mb4_unicode_ci,
  `eta_message` text COLLATE utf8mb4_unicode_ci,
  `pilotage_compulsory` text COLLATE utf8mb4_unicode_ci,
  `pilotage_available` text COLLATE utf8mb4_unicode_ci,
  `pilotage_local_assist` text COLLATE utf8mb4_unicode_ci,
  `pilotage_advisable` text COLLATE utf8mb4_unicode_ci,
  `tugs_salvage` text COLLATE utf8mb4_unicode_ci,
  `tugs_assist` text COLLATE utf8mb4_unicode_ci,
  `quarantine_pratique` text COLLATE utf8mb4_unicode_ci,
  `quarantine_deratt_cert` text COLLATE utf8mb4_unicode_ci,
  `quarantine_other` text COLLATE utf8mb4_unicode_ci,
  `communications_telephone` text COLLATE utf8mb4_unicode_ci,
  `communications_telegraph` text COLLATE utf8mb4_unicode_ci,
  `communications_radio` text COLLATE utf8mb4_unicode_ci,
  `communications_radio_tel` text COLLATE utf8mb4_unicode_ci,
  `communications_air` text COLLATE utf8mb4_unicode_ci,
  `communications_rail` text COLLATE utf8mb4_unicode_ci,
  `load_offload_wharves` text COLLATE utf8mb4_unicode_ci,
  `load_offload_anchor` text COLLATE utf8mb4_unicode_ci,
  `load_offload_med_moor` text COLLATE utf8mb4_unicode_ci,
  `load_offload_beach_moor` text COLLATE utf8mb4_unicode_ci,
  `load_offload_ice_moor` text COLLATE utf8mb4_unicode_ci,
  `medical_facilities` text COLLATE utf8mb4_unicode_ci,
  `garbage_disposal` text COLLATE utf8mb4_unicode_ci,
  `degauss` text COLLATE utf8mb4_unicode_ci,
  `dirty_ballast` text COLLATE utf8mb4_unicode_ci,
  `cranes_fixed` text COLLATE utf8mb4_unicode_ci,
  `cranes_mobile` text COLLATE utf8mb4_unicode_ci,
  `cranes_floating` text COLLATE utf8mb4_unicode_ci,
  `lifts_100_tons_plus` text COLLATE utf8mb4_unicode_ci,
  `lifts_50_100_tons` text COLLATE utf8mb4_unicode_ci,
  `lifts_25_49_tons` text COLLATE utf8mb4_unicode_ci,
  `lifts_0_24_tons` text COLLATE utf8mb4_unicode_ci,
  `services_longshore` text COLLATE utf8mb4_unicode_ci,
  `services_elect` text COLLATE utf8mb4_unicode_ci,
  `services_steam` text COLLATE utf8mb4_unicode_ci,
  `services_navig_equip` text COLLATE utf8mb4_unicode_ci,
  `services_elect_repair` text COLLATE utf8mb4_unicode_ci,
  `supplies_provisions` text COLLATE utf8mb4_unicode_ci,
  `supplies_water` text COLLATE utf8mb4_unicode_ci,
  `supplies_fuel_oil` text COLLATE utf8mb4_unicode_ci,
  `supplies_diesel_oil` text COLLATE utf8mb4_unicode_ci,
  `supplies_deck` text COLLATE utf8mb4_unicode_ci,
  `supplies_engine` text COLLATE utf8mb4_unicode_ci,
  `repair_code` text COLLATE utf8mb4_unicode_ci,
  `drydock` text COLLATE utf8mb4_unicode_ci,
  `railway` text COLLATE utf8mb4_unicode_ci
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Pengeluaran data tidak dipilih.

-- membuang struktur untuk table asetpedia.wpi_import
CREATE TABLE IF NOT EXISTS `wpi_import` (
  `world_port_index_number` int DEFAULT NULL,
  `region_index` int DEFAULT NULL,
  `main_port_name` text COLLATE utf8mb4_unicode_ci,
  `wpi_country_code` text COLLATE utf8mb4_unicode_ci,
  `latitude_degrees` int DEFAULT NULL,
  `latitude_minutes` int DEFAULT NULL,
  `latitude_hemisphere` text COLLATE utf8mb4_unicode_ci,
  `longitude_degrees` int DEFAULT NULL,
  `longitude_minutes` int DEFAULT NULL,
  `longitude_hemisphere` text COLLATE utf8mb4_unicode_ci,
  `publication` text COLLATE utf8mb4_unicode_ci,
  `chart` text COLLATE utf8mb4_unicode_ci,
  `harbor_size_code` text COLLATE utf8mb4_unicode_ci,
  `harbor_type_code` text COLLATE utf8mb4_unicode_ci,
  `shelter_afforded_code` text COLLATE utf8mb4_unicode_ci,
  `entrance_restriction_tide` text COLLATE utf8mb4_unicode_ci,
  `entrance_restriction_swell` text COLLATE utf8mb4_unicode_ci,
  `entrance_restriction_ice` text COLLATE utf8mb4_unicode_ci,
  `entrance_restriction_other` text COLLATE utf8mb4_unicode_ci,
  `overhead_limits` text COLLATE utf8mb4_unicode_ci,
  `channel_depth` text COLLATE utf8mb4_unicode_ci,
  `anchorage_depth` text COLLATE utf8mb4_unicode_ci,
  `cargo_pier_depth` text COLLATE utf8mb4_unicode_ci,
  `oil_terminal_depth` text COLLATE utf8mb4_unicode_ci,
  `tide` int DEFAULT NULL,
  `maxsize_vessel_code` text COLLATE utf8mb4_unicode_ci,
  `good_holding_ground` text COLLATE utf8mb4_unicode_ci,
  `turning_area` text COLLATE utf8mb4_unicode_ci,
  `first_port_of_entry` text COLLATE utf8mb4_unicode_ci,
  `us_representative` text COLLATE utf8mb4_unicode_ci,
  `eta_message` text COLLATE utf8mb4_unicode_ci,
  `pilotage_compulsory` text COLLATE utf8mb4_unicode_ci,
  `pilotage_available` text COLLATE utf8mb4_unicode_ci,
  `pilotage_local_assist` text COLLATE utf8mb4_unicode_ci,
  `pilotage_advisable` text COLLATE utf8mb4_unicode_ci,
  `tugs_salvage` text COLLATE utf8mb4_unicode_ci,
  `tugs_assist` text COLLATE utf8mb4_unicode_ci,
  `quarantine_pratique` text COLLATE utf8mb4_unicode_ci,
  `quarantine_deratt_cert` text COLLATE utf8mb4_unicode_ci,
  `quarantine_other` text COLLATE utf8mb4_unicode_ci,
  `communications_telephone` text COLLATE utf8mb4_unicode_ci,
  `communications_telegraph` text COLLATE utf8mb4_unicode_ci,
  `communications_radio` text COLLATE utf8mb4_unicode_ci,
  `communications_radio_tel` text COLLATE utf8mb4_unicode_ci,
  `communications_air` text COLLATE utf8mb4_unicode_ci,
  `communications_rail` text COLLATE utf8mb4_unicode_ci,
  `load_offload_wharves` text COLLATE utf8mb4_unicode_ci,
  `load_offload_anchor` text COLLATE utf8mb4_unicode_ci,
  `load_offload_med_moor` text COLLATE utf8mb4_unicode_ci,
  `load_offload_beach_moor` text COLLATE utf8mb4_unicode_ci,
  `load_offload_ice_moor` text COLLATE utf8mb4_unicode_ci,
  `medical_facilities` text COLLATE utf8mb4_unicode_ci,
  `garbage_disposal` text COLLATE utf8mb4_unicode_ci,
  `degauss` text COLLATE utf8mb4_unicode_ci,
  `dirty_ballast` text COLLATE utf8mb4_unicode_ci,
  `cranes_fixed` text COLLATE utf8mb4_unicode_ci,
  `cranes_mobile` text COLLATE utf8mb4_unicode_ci,
  `cranes_floating` text COLLATE utf8mb4_unicode_ci,
  `lifts_100_tons_plus` text COLLATE utf8mb4_unicode_ci,
  `lifts_50_100_tons` text COLLATE utf8mb4_unicode_ci,
  `lifts_25_49_tons` text COLLATE utf8mb4_unicode_ci,
  `lifts_0_24_tons` text COLLATE utf8mb4_unicode_ci,
  `services_longshore` text COLLATE utf8mb4_unicode_ci,
  `services_elect` text COLLATE utf8mb4_unicode_ci,
  `services_steam` text COLLATE utf8mb4_unicode_ci,
  `services_navig_equip` text COLLATE utf8mb4_unicode_ci,
  `services_elect_repair` text COLLATE utf8mb4_unicode_ci,
  `supplies_provisions` text COLLATE utf8mb4_unicode_ci,
  `supplies_water` text COLLATE utf8mb4_unicode_ci,
  `supplies_fuel_oil` text COLLATE utf8mb4_unicode_ci,
  `supplies_diesel_oil` text COLLATE utf8mb4_unicode_ci,
  `supplies_deck` text COLLATE utf8mb4_unicode_ci,
  `supplies_engine` text COLLATE utf8mb4_unicode_ci,
  `repair_code` text COLLATE utf8mb4_unicode_ci,
  `drydock` text COLLATE utf8mb4_unicode_ci,
  `railway` text COLLATE utf8mb4_unicode_ci,
  `latitude` decimal(12,9) DEFAULT NULL,
  `longitude` decimal(12,9) DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Pengeluaran data tidak dipilih.

-- membuang struktur untuk table asetpedia.wpi_region
CREATE TABLE IF NOT EXISTS `wpi_region` (
  `world_port_index_number` int DEFAULT NULL,
  `area_name` text COLLATE utf8mb4_unicode_ci
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Pengeluaran data tidak dipilih.

/*!40103 SET TIME_ZONE=IFNULL(@OLD_TIME_ZONE, 'system') */;
/*!40101 SET SQL_MODE=IFNULL(@OLD_SQL_MODE, '') */;
/*!40014 SET FOREIGN_KEY_CHECKS=IFNULL(@OLD_FOREIGN_KEY_CHECKS, 1) */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40111 SET SQL_NOTES=IFNULL(@OLD_SQL_NOTES, 1) */;
