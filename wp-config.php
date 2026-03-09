<?php
/**
 * The base configuration for WordPress
 *
 * The wp-config.php creation script uses this file during the installation.
 * You don't have to use the website, you can copy this file to "wp-config.php"
 * and fill in the values.
 *
 * This file contains the following configurations:
 *
 * * Database settings
 * * Secret keys
 * * Database table prefix
 * * ABSPATH
 *
 * @link https://developer.wordpress.org/advanced-administration/wordpress/wp-config/
 *
 * @package WordPress
 */

// ** Database settings - You can get this info from your web host ** //
/** The name of the database for WordPress */
define( 'DB_NAME', 'easymotor' );

/** Database username */
define( 'DB_USER', 'easymotor' );

/** Database password */
define( 'DB_PASSWORD', 'tjdgns12!' );

/** Database hostname */
define( 'DB_HOST', 'localhost' );

/** Database charset to use in creating database tables. */
define( 'DB_CHARSET', 'utf8mb4' );

/** The database collate type. Don't change this if in doubt. */
define( 'DB_COLLATE', '' );

/**#@+
 * Authentication unique keys and salts.
 *
 * Change these to different unique phrases! You can generate these using
 * the {@link https://api.wordpress.org/secret-key/1.1/salt/ WordPress.org secret-key service}.
 *
 * You can change these at any point in time to invalidate all existing cookies.
 * This will force all users to have to log in again.
 *
 * @since 2.6.0
 */
define( 'AUTH_KEY',         '5?nAq` Oyi$)(?z:j=*e94{=!qQHW:}c&aYmBbSZ,{Z?ITXYyoee&pmlG#VDaimx' );
define( 'SECURE_AUTH_KEY',  '(s|Z|C1itSps<*wi^RWz]$Z&OtF=])}CufFCIq-qmEO`|iT: *?LYbPs^iXPSE_<' );
define( 'LOGGED_IN_KEY',    'Rx*^D_x%P,Tr#f5|;8aC1]c2&,!xRMEe0yU{bE+zHUIiA@,_~GT:A#7]&#niB*vh' );
define( 'NONCE_KEY',        '1t^w}T<_pJBvcNY?Z$Tj$nIeB~f8G!l$^U?bWl,<4RY+wk%[_y,1p=!^Ub( iV>5' );
define( 'AUTH_SALT',        'ZqhWyX]],@lmY`U[|_et)c5YI^4rR4vhNT2gWVSgUpk>QLFZFg.94`5IKy/7R{s2' );
define( 'SECURE_AUTH_SALT', 'yZWD=c-/2A7Bo`i]X7%J[lM>X?Sfy.>*<&sNcz0g2~&=TD~kceaG|)E#bE0?d,<|' );
define( 'LOGGED_IN_SALT',   '-<^@Mf`m-7C0ChQU+em!3H^N<U^Q0pWgDIt`LA:Ykp#jeHfM7<wkP`9%quJn}I(0' );
define( 'NONCE_SALT',       'pgU<O4*0SJV$grA^u},G3vJsLXIh2!<G3)-F`=0Dst-4!81-UMjKADKgHlz8$nSO' );

/**#@-*/

/**
 * WordPress database table prefix.
 *
 * You can have multiple installations in one database if you give each
 * a unique prefix. Only numbers, letters, and underscores please!
 */
$table_prefix = 'wp_';

/**
 * For developers: WordPress debugging mode.
 *
 * Change this to true to enable the display of notices during development.
 * It is strongly recommended that plugin and theme developers use WP_DEBUG
 * in their development environments.
 *
 * For information on other constants that can be used for debugging,
 * visit the documentation.
 *
 * @link https://developer.wordpress.org/advanced-administration/debug/debug-wordpress/
 */
define( 'WP_DEBUG', false );

/* Add any custom values between this line and the "stop editing" line. */

/** 메모리 제한 늘리기 (Elementor 권장) */
define( 'WP_MEMORY_LIMIT', '512M' );
define( 'WP_MAX_MEMORY_LIMIT', '512M' );

/* That's all, stop editing! Happy publishing. */

/** Absolute path to the WordPress directory. */
if ( ! defined( 'ABSPATH' ) ) {
	define( 'ABSPATH', __DIR__ . '/' );
}

/** Sets up WordPress vars and included files. */
require_once ABSPATH . 'wp-settings.php';
