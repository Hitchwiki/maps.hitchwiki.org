SET SQL_MODE="NO_AUTO_VALUE_ON_ZERO";


/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!40101 SET NAMES utf8 */;

--
-- Database: `hitchwiki_maps`
--

-- --------------------------------------------------------

--
-- Table structure for table `geo_cities`
--

CREATE TABLE IF NOT EXISTS `geo_cities` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `country` varchar(2) COLLATE utf8_bin NOT NULL,
  `city` varchar(128) COLLATE utf8_bin NOT NULL,
  `lat` double NOT NULL,
  `lng` double NOT NULL,
  PRIMARY KEY (`id`)
) ENGINE=MyISAM  DEFAULT CHARSET=utf8 COLLATE=utf8_bin;

-- --------------------------------------------------------

--
-- Table structure for table `t_comments`
--

CREATE TABLE IF NOT EXISTS `t_comments` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `fk_place` int(11) NOT NULL,
  `fk_user` int(11) DEFAULT NULL,
  `nick` varchar(80) CHARACTER SET utf8 DEFAULT NULL,
  `comment` text CHARACTER SET utf8 NOT NULL,
  `datetime` datetime NOT NULL,
  `hidden` tinyint(1) DEFAULT NULL,
  `ip` varchar(15) CHARACTER SET utf8 DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=MyISAM  DEFAULT CHARSET=latin1;

-- --------------------------------------------------------

--
-- Table structure for table `t_countries`
--

CREATE TABLE IF NOT EXISTS `t_countries` (
  `iso` char(2) CHARACTER SET utf8 NOT NULL,
  `en_UK` varchar(80) CHARACTER SET utf8 NOT NULL COMMENT 'Name in English',
  `lv_LV` varchar(80) CHARACTER SET utf8 DEFAULT NULL COMMENT 'Latvian',
  `en@pirate` varchar(80) CHARACTER SET utf8 DEFAULT NULL COMMENT 'In English (pirate)',
  `de_DE` varchar(80) CHARACTER SET utf8 DEFAULT NULL COMMENT 'German',
  `fi_FI` varchar(80) CHARACTER SET utf8 DEFAULT NULL COMMENT 'Finnish',
  `es_ES` varchar(80) CHARACTER SET utf8 DEFAULT NULL COMMENT 'Spanish',
  `ru_RU` varchar(80) CHARACTER SET utf8 DEFAULT NULL COMMENT 'Russian',
  `lt_LT` varchar(80) CHARACTER SET utf8 DEFAULT NULL COMMENT 'Lithuanian',
  `nl_NL` varchar(80) CHARACTER SET utf8 DEFAULT NULL COMMENT 'Dutch',
  `ro_RO` varchar(80) CHARACTER SET utf8 DEFAULT NULL COMMENT 'Romanian',
  `pt_PT` varchar(80) CHARACTER SET utf8 DEFAULT NULL COMMENT 'Portuguese',
  `pl_PL` varchar(80) CHARACTER SET utf8 DEFAULT NULL COMMENT 'Polish',
  `zh_CN` varchar(80) CHARACTER SET utf8 DEFAULT NULL COMMENT 'Simplified Chinese',
  `sv_SE` varchar(80) CHARACTER SET utf8 DEFAULT NULL COMMENT 'Swedish',
  `fr_FR` varchar(80) CHARACTER SET utf8 DEFAULT NULL COMMENT 'French',
  `it_IT` varchar(80) CHARACTER SET utf8 DEFAULT NULL COMMENT 'Italian',
  `iso3` char(3) CHARACTER SET utf8 DEFAULT NULL,
  `numcode` smallint(6) DEFAULT NULL,
  `continent` varchar(2) CHARACTER SET utf8 DEFAULT NULL,
  `lat` float DEFAULT NULL COMMENT 'in google projection',
  `lon` float DEFAULT NULL COMMENT 'in google projection',
  `zoom` int(11) DEFAULT '5',
  `bBoxWest` float DEFAULT NULL,
  `bBoxNorth` float DEFAULT NULL,
  `bBoxEast` float DEFAULT NULL,
  `bBoxSouth` float DEFAULT NULL,
  PRIMARY KEY (`iso`)
) ENGINE=MyISAM DEFAULT CHARSET=utf8 COLLATE=utf8_unicode_ci;

-- --------------------------------------------------------

--
-- Table structure for table `t_points`
--

CREATE TABLE IF NOT EXISTS `t_points` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `user` int(11) DEFAULT NULL COMMENT 'user id',
  `type` int(11) DEFAULT NULL,
  `trip_id` int(11) DEFAULT NULL,
  `lat` double NOT NULL DEFAULT '0',
  `lon` double NOT NULL DEFAULT '0',
  `elevation` int(11) DEFAULT NULL COMMENT 'altitude in meters from the sea level',
  `date_begin` date DEFAULT NULL,
  `date_end` date DEFAULT NULL,
  `rating` int(11) NOT NULL DEFAULT '0',
  `rating_count` int(11) NOT NULL DEFAULT '0' COMMENT 'count of ratings',
  `waitingtime` int(3) DEFAULT NULL COMMENT 'in minutes',
  `waitingtime_count` int(3) NOT NULL DEFAULT '0',
  `country` varchar(64) CHARACTER SET utf8 NOT NULL DEFAULT '' COMMENT 'ISO-code',
  `continent` varchar(2) CHARACTER SET utf8 DEFAULT NULL COMMENT 'shortcode',
  `locality` varchar(128) CHARACTER SET utf8 COLLATE utf8_unicode_ci DEFAULT NULL COMMENT 'city name',
  `datetime` datetime DEFAULT NULL COMMENT 'markers added before 08/2010 are usually NULL.',
  `debug` varchar(11) COLLATE utf8_bin DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=MyISAM  DEFAULT CHARSET=utf8 COLLATE=utf8_bin;

-- --------------------------------------------------------

--
-- Table structure for table `t_points_descriptions`
--

CREATE TABLE IF NOT EXISTS `t_points_descriptions` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `datetime` datetime DEFAULT NULL,
  `language` varchar(6) NOT NULL DEFAULT 'en_UK',
  `fk_point` varchar(11) NOT NULL,
  `fk_user` varchar(11) DEFAULT NULL,
  `ip` varchar(15) DEFAULT NULL,
  `description` text,
  PRIMARY KEY (`id`)
) ENGINE=MyISAM  DEFAULT CHARSET=utf8;

-- --------------------------------------------------------

--
-- Table structure for table `t_ptransport`
--

CREATE TABLE IF NOT EXISTS `t_ptransport` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `city` varchar(80) DEFAULT NULL,
  `country` varchar(2) DEFAULT NULL,
  `URL` varchar(255) DEFAULT '',
  `title` varchar(255) DEFAULT NULL,
  `type` varchar(255) DEFAULT NULL,
  `datetime` datetime DEFAULT NULL,
  `user_id` int(11) DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=MyISAM  DEFAULT CHARSET=utf8;

-- --------------------------------------------------------

--
-- Table structure for table `t_ratings`
--

CREATE TABLE IF NOT EXISTS `t_ratings` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `fk_user` int(11) DEFAULT NULL,
  `fk_point` int(11) NOT NULL DEFAULT '0',
  `rating` int(11) NOT NULL DEFAULT '0',
  `datetime` datetime DEFAULT NULL,
  `ip` varchar(15) DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_point` (`fk_point`)
) ENGINE=MyISAM  DEFAULT CHARSET=utf8;

-- --------------------------------------------------------

--
-- Table structure for table `t_users`
--

CREATE TABLE IF NOT EXISTS `t_users` (
  `id` int(11) NOT NULL,
  `name` varchar(255) CHARACTER SET utf8 COLLATE utf8_unicode_ci NOT NULL,
  `email` varchar(255) NOT NULL DEFAULT '',
  `registered` date DEFAULT NULL,
  `last_seen` datetime DEFAULT NULL,
  `location` varchar(255) DEFAULT NULL COMMENT 'most likely a city',
  `country` varchar(2) DEFAULT NULL COMMENT 'country iso code',
  `language` varchar(11) DEFAULT 'en_UK' COMMENT 'languagecode, eg. de_DE',
  `private_location` int(1) DEFAULT NULL COMMENT '1=true',
  `google_latitude` varchar(30) DEFAULT NULL COMMENT 'google latitude ID',
  `centered_glatitude` int(1) DEFAULT NULL COMMENT 'Is Maps centered to Google Latitude point?',
  `allow_gravatar` int(1) DEFAULT NULL,
  `map_google` int(1) DEFAULT '1',
  `map_yahoo` int(1) DEFAULT NULL,
  `map_vearth` int(1) DEFAULT NULL,
  `map_default_layer` varchar(10) DEFAULT NULL,
  `admin` int(1) DEFAULT NULL COMMENT '1=yes',
  PRIMARY KEY (`id`)
) ENGINE=MyISAM  DEFAULT CHARSET=utf8;

-- --------------------------------------------------------

--
-- Table structure for table `t_waitingtimes`
--

CREATE TABLE IF NOT EXISTS `t_waitingtimes` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `fk_user` int(11) DEFAULT NULL,
  `fk_point` int(11) NOT NULL DEFAULT '0',
  `waitingtime` int(3) NOT NULL COMMENT 'in minutes',
  `datetime` datetime DEFAULT NULL,
  `ip` varchar(15) DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_point` (`fk_point`)
) ENGINE=MyISAM  DEFAULT CHARSET=utf8;
