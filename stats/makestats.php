<?php
include "db.inc.php";

$count = 0;
$res = mysql_query("SELECT country, count(*) AS cnt
                    FROM t_points
                    WHERE type=1
                    GROUP BY country
                    ORDER BY cnt DESC");
while ($row = mysql_fetch_array($res)) {
    $country[getCountryFromCode($row['country'])] = $row['cnt'];
    $count += $row['cnt'];
}

$hitchbase = trim(file_get_contents("/tmp/hb.cnt"));
$liftershalte = $count;

$query = "INSERT INTO stats_main (date, hitchbase, liftershalte) VALUES (NOW(), '$hitchbase', '$liftershalte')";
mysql_query($query);
$id = mysql_insert_id();
foreach ($country AS $c => $cnt) {
    $query = "INSERT INTO stats_countries (fk_stats_main_id, country, count) VALUES ($id, '$c', '$cnt')";
    mysql_query($query);
}
?>
