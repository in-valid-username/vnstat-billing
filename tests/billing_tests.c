#include "common.h"
#include "vnstat_tests.h"
#include "billing_tests.h"
#include "cfg.h"
#include "dbsql.h"
#include "misc.h"
#include "datacache.h"
#include "daemon.h"
#include "ifinfo.h"

static void billing_fixture(void)
{
	setup();
	setenv("TZ", "UTC", 1);
	tzset();
	clean_testdbdir();
	strcpy(cfg.dbdir, TESTDBDIR);
}

START_TEST(billing_config_validation)
{
	int minute;
	for (minute = 0; minute < 60; minute++) {
		cfg.monthrotatehour = 23;
		cfg.monthrotateminute = minute;
		validatecfg(CT_All);
		ck_assert_int_eq(cfg.monthrotatehour, 23);
		ck_assert_int_eq(cfg.monthrotateminute, minute);
	}
	disable_logprints();
	cfg.monthrotatehour = 24;
	cfg.monthrotateminute = -1;
	validatecfg(CT_All);
	ck_assert_int_eq(cfg.monthrotatehour, 0);
	ck_assert_int_eq(cfg.monthrotateminute, 0);
	cfg.monthrotatehour = -1;
	cfg.monthrotateminute = 60;
	validatecfg(CT_All);
	ck_assert_int_eq(cfg.monthrotatehour, 0);
	ck_assert_int_eq(cfg.monthrotateminute, 0);
}
END_TEST

START_TEST(billing_minute_database_boundary)
{
	const char *zones[] = {"UTC", "Asia/Singapore", "America/New_York"};
	dbdatalist *data = NULL;
	dbdatalistinfo info;
	time_t boundary;
	int minute;

	setenv("TZ", zones[_i / 2], 1);
	tzset();
	cfg.useutc = _i % 2;
	validatecfg(CT_All);
	cfg.monthrotate = 7;
	cfg.monthrotatehour = 18;
	cfg.monthrotateyears = 1;
	ck_assert_int_eq(db_open_rw(1), 1);
	for (minute = 0; minute < 60; minute++) {
		cfg.monthrotateminute = minute;
		ck_assert_int_eq(db_addinterface("minute0"), 1);
		boundary = (time_t)get_timestamp(2024, 1, 7, 18, minute);
		ck_assert_int_eq(db_addtraffic_dated("minute0", 10, 20, (uint64_t)(boundary - 1)), 1);
		ck_assert_int_eq(db_addtraffic_dated("minute0", 30, 40, (uint64_t)boundary), 1);
		ck_assert_int_eq(db_addtraffic_dated("minute0", 50, 60, (uint64_t)(boundary + 1)), 1);
		ck_assert_int_eq(db_getdata(&data, &info, "minute0", "month", 0), 1);
		ck_assert_int_eq(info.count, 2);
		ck_assert_int_eq(data->rx, 10);
		ck_assert_int_eq(data->tx, 20);
		ck_assert_int_eq(data->next->rx, 80);
		ck_assert_int_eq(data->next->tx, 100);
		dbdatalistfree(&data);
		ck_assert_int_eq(db_getdata(&data, &info, "minute0", "year", 0), 1);
		ck_assert_int_eq(info.count, 2);
		ck_assert_int_eq(data->rx, 10);
		ck_assert_int_eq(data->next->rx, 80);
		dbdatalistfree(&data);
		ck_assert_int_eq(db_removeinterface("minute0"), 1);
	}
	ck_assert_int_eq(db_close(), 1);
}
END_TEST

START_TEST(billing_minute_cache_separates_periods)
{
	const char *zones[] = {"UTC", "Asia/Singapore", "America/New_York"};
	DSTATE state;
	dbdatalist *data = NULL;
	dbdatalistinfo info;
	interfaceinfo totals;
	time_t boundary, step;
	int minute, i;

	initdstate(&state);
	strcpy(cfg.dbdir, TESTDBDIR);
	setenv("TZ", zones[_i / 2], 1);
	tzset();
	cfg.useutc = _i % 2;
	validatecfg(CT_All);
	cfg.monthrotate = 7;
	cfg.monthrotatehour = 18;
	cfg.monthrotateyears = 1;
	ck_assert_int_eq(db_open_rw(1), 1);
	for (minute = 0; minute < 60; minute++) {
		cfg.monthrotateminute = minute;
		boundary = (time_t)get_timestamp(2024, 1, 7, 18, minute);
		ck_assert_int_eq(db_addinterface("minute0"), 1);
		ck_assert_int_eq(datacache_add(&state.dcache, "minute0", 0), 1);
		state.dcache->updated = boundary - 20;
		for (i = 0; i < 3; i++) {
			step = boundary + i * 20;
			ifinfo.timestamp = step;
			ifinfo.rx = (uint64_t)((i + 1) * 10);
			ifinfo.tx = (uint64_t)((i + 1) * 20);
			ifinfo.is64bit = 1;
			ck_assert_int_eq(processifinfo(&state, &state.dcache), 1);
		}
		ck_assert_ptr_ne(state.dcache->log, NULL);
		ck_assert_int_eq(state.dcache->log->timestamp,
			boundary - (boundary % (minute % 5 ? 60 : 300)));
		flushcachetodisk(&state);
		ck_assert_int_eq(db_errcode, 0);
		ck_assert_ptr_eq(state.dcache->log, NULL);
		flushcachetodisk(&state);
		ck_assert_int_eq(db_errcode, 0);
		ck_assert_int_eq(db_getdata(&data, &info, "minute0", "month", 0), 1);
		ck_assert_int_eq(info.count, 2);
		ck_assert_int_eq(data->rx, 10);
		ck_assert_int_eq(data->tx, 20);
		ck_assert_int_eq(data->next->rx, 20);
		ck_assert_int_eq(data->next->tx, 40);
		dbdatalistfree(&data);
		ck_assert_int_eq(db_getdata(&data, &info, "minute0", "year", 0), 1);
		ck_assert_int_eq(info.count, 2);
		ck_assert_int_eq(data->rx, 10);
		ck_assert_int_eq(data->next->rx, 20);
		dbdatalistfree(&data);
		ck_assert_int_eq(db_getdata(&data, &info, "minute0", "fiveminute", 0), 1);
		ck_assert_int_eq(info.count, minute % 5 ? 1 : 2);
		ck_assert_int_eq(info.sumrx, 30);
		ck_assert_int_eq(info.sumtx, 60);
		dbdatalistfree(&data);
		ck_assert_int_eq(db_getinterfaceinfo_epoch("minute0", &totals), 1);
		ck_assert_int_eq(totals.rxtotal, 30);
		ck_assert_int_eq(totals.txtotal, 60);
		datacache_clear(&state.dcache);
		ck_assert_int_eq(db_removeinterface("minute0"), 1);
	}
	ck_assert_int_eq(db_close(), 1);
}
END_TEST

START_TEST(billing_minute_straddling_sample_keeps_upstream_attribution)
{
	DSTATE state;
	dbdatalist *data = NULL;
	dbdatalistinfo info;
	time_t boundary;

	initdstate(&state);
	strcpy(cfg.dbdir, TESTDBDIR);
	cfg.monthrotate = 7;
	cfg.monthrotatehour = 18;
	cfg.monthrotateminute = _i;
	boundary = (time_t)get_timestamp(2024, 1, 7, 18, _i);
	ck_assert_int_eq(db_open_rw(1), 1);
	ck_assert_int_eq(db_addinterface("minute0"), 1);
	ck_assert_int_eq(datacache_add(&state.dcache, "minute0", 0), 1);
	state.dcache->updated = boundary - 10;
	ifinfo.timestamp = boundary + 10;
	ifinfo.rx = 50;
	ifinfo.tx = 70;
	ifinfo.is64bit = 1;
	ck_assert_int_eq(processifinfo(&state, &state.dcache), 1);
	ifinfo.timestamp = boundary + 30;
	ifinfo.rx = 80;
	ifinfo.tx = 110;
	ck_assert_int_eq(processifinfo(&state, &state.dcache), 1);
	flushcachetodisk(&state);
	ck_assert_int_eq(db_errcode, 0);
	ck_assert_int_eq(db_getdata(&data, &info, "minute0", "month", 0), 1);
	ck_assert_int_eq(info.count, 2);
	/* A counter interval crossing the cutoff cannot be split from these readings. */
	ck_assert_int_eq(data->rx, 50);
	ck_assert_int_eq(data->tx, 70);
	ck_assert_int_eq(data->next->rx, 30);
	ck_assert_int_eq(data->next->tx, 40);
	ck_assert_int_eq(info.sumrx, 80);
	ck_assert_int_eq(info.sumtx, 110);
	dbdatalistfree(&data);
	datacache_clear(&state.dcache);
	ck_assert_int_eq(db_close(), 1);
}
END_TEST

START_TEST(billing_database_boundary)
{
	const char *zones[] = {"UTC", "Asia/Singapore", "America/New_York"};
	dbdatalist *data = NULL;
	dbdatalistinfo info;
	time_t boundary;
	char label[32];

	setenv("TZ", zones[_i / 2], 1);
	tzset();
	cfg.useutc = _i % 2;
	validatecfg(CT_All);
	cfg.monthrotate = 7;
	cfg.monthrotatehour = 18;
	cfg.monthrotateminute = 25;
	cfg.monthrotateyears = 1;
	ck_assert_int_eq(db_open_rw(1), 1);
	ck_assert_int_eq(db_addinterface("billing0"), 1);
	boundary = (time_t)get_timestamp(2024, 1, 7, 18, 25);
	ck_assert_int_eq(db_addtraffic_dated("billing0", 10, 20, (uint64_t)(boundary - 300)), 1);
	ck_assert_int_eq(db_addtraffic_dated("billing0", 30, 40, (uint64_t)boundary), 1);
	ck_assert_int_eq(db_addtraffic_dated("billing0", 50, 60, (uint64_t)(boundary + 300)), 1);
	ck_assert_int_eq(db_getdata(&data, &info, "billing0", "month", 0), 1);
	ck_assert_int_eq(info.count, 2);
	ck_assert_int_eq(data->rx, 10);
	strftime(label, sizeof(label), "%Y-%m-%d", localtime(&data->timestamp));
	ck_assert_str_eq(label, "2023-12-01");
	ck_assert_int_eq(data->next->rx, 80);
	ck_assert_int_eq(data->next->tx, 100);
	strftime(label, sizeof(label), "%Y-%m-%d", localtime(&data->next->timestamp));
	ck_assert_str_eq(label, "2024-01-01");
	/* Query timestamps use the database calendar, including with UseUTC. */
	ck_assert_int_eq(getperiodseconds(LT_Month, data->next->timestamp,
	                                data->next->timestamp + 7 * 86400, 0, 0), 31 * 86400);
	dbdatalistfree(&data);
	ck_assert_int_eq(db_getdata(&data, &info, "billing0", "year", 0), 1);
	ck_assert_int_eq(info.count, 2);
	ck_assert_int_eq(data->rx, 10);
	ck_assert_int_eq(data->next->rx, 80);
	dbdatalistfree(&data);
	ck_assert_int_eq(db_close(), 1);
}
END_TEST

START_TEST(billing_first_day_nonmidnight)
{
	dbdatalist *data = NULL;
	dbdatalistinfo info;
	cfg.monthrotatehour = 1;
	cfg.monthrotateminute = 5;
	ck_assert_int_eq(db_open_rw(1), 1);
	ck_assert_int_eq(db_addinterface("billing0"), 1);
	ck_assert_int_eq(db_addtraffic_dated("billing0", 10, 20, get_timestamp(2024, 1, 1, 1, 0)), 1);
	ck_assert_int_eq(db_addtraffic_dated("billing0", 30, 40, get_timestamp(2024, 1, 1, 1, 5)), 1);
	ck_assert_int_eq(db_getdata(&data, &info, "billing0", "month", 0), 1);
	ck_assert_int_eq(info.count, 2);
	ck_assert_int_eq(data->rx, 10);
	ck_assert_int_eq(data->next->rx, 30);
	dbdatalistfree(&data);
	/* Annual data remains calendar-based unless explicitly opted in. */
	ck_assert_int_eq(db_getdata(&data, &info, "billing0", "year", 0), 1);
	ck_assert_int_eq(info.count, 1);
	ck_assert_int_eq(data->rx, 40);
	dbdatalistfree(&data);
	ck_assert_int_eq(db_close(), 1);
}
END_TEST

START_TEST(billing_periods_and_estimates)
{
	time_t label, start, end;
	uint64_t rx, tx;
	dbdatalist *data = NULL;
	cfg.monthrotate = 7;
	cfg.monthrotatehour = 18;
	cfg.monthrotateminute = 24;
	label = (time_t)get_timestamp(2024, 2, 1, 0, 0);
	start = (time_t)get_timestamp(2024, 2, 7, 18, 24);
	end = (time_t)get_timestamp(2024, 3, 7, 18, 24);
	ck_assert_int_eq(billingperiodstart(label, 0, 0), start);
	ck_assert_int_eq(billingperiodstart(label, 0, 1), end);
	ck_assert_int_eq(issametimeslot(LT_Month, label, start - 1), 0);
	ck_assert_int_eq(issametimeslot(LT_Month, label, start), 1);
	ck_assert_int_eq(issametimeslot(LT_Month, label, end - 1), 1);
	ck_assert_int_eq(issametimeslot(LT_Month, label, end), 0);
	ck_assert_int_eq(mosecs(label, start - 1), 1);
	ck_assert_int_eq(mosecs(label, start + 300), 300);
	ck_assert_int_eq(getperiodseconds(LT_Month, label, start + 600, start + 300, 1), 300);
	ck_assert_int_eq(getperiodseconds(LT_Month, label, end, 0, 0), 29 * 86400);
	ck_assert_int_eq(dbdatalistadd(&data, 1000, 2000, label, 1), 1);
	getestimates(&rx, &tx, LT_Month, start + 1000, 0, &data);
	ck_assert_int_eq(rx, 29 * 86400);
	ck_assert_int_eq(tx, 2 * 29 * 86400);
	dbdatalistfree(&data);
	/* Leap-year duration comes from the entry year, not today's year. */
	label = (time_t)get_timestamp(2023, 2, 1, 0, 0);
	ck_assert_int_eq(getperiodseconds(LT_Month, label, 0, 0, 0), 28 * 86400);
	/* Local billing months preserve the local wall-clock boundary across DST. */
	setenv("TZ", "America/New_York", 1);
	tzset();
	label = (time_t)get_timestamp(2024, 3, 1, 0, 0);
	ck_assert_int_eq(getperiodseconds(LT_Month, label, 0, 0, 0), 31 * 86400 - 3600);
}
END_TEST

START_TEST(billing_direct_import_preserves_labels)
{
	const char *sql;
	cfg.monthrotate = 7;
	cfg.monthrotatehour = 18;
	cfg.monthrotateminute = 25;
	cfg.monthrotateyears = 1;
	sql = db_get_date_generator(3, 1, "'2024-01-01'");
	ck_assert_ptr_eq(strstr(sql, "minutes"), NULL);
	sql = db_get_date_generator(4, 1, "'2024-01-01'");
	ck_assert_ptr_eq(strstr(sql, "minutes"), NULL);
}
END_TEST

START_TEST(billing_cache_uses_real_epoch)
{
	const char *zones[] = {"UTC", "Asia/Singapore", "America/New_York"};
	DSTATE state;
	time_t timestamp;
	initdstate(&state);
	strcpy(cfg.dbdir, TESTDBDIR);
	setenv("TZ", zones[_i / 4], 1);
	tzset();
	cfg.useutc = _i % 2;
	validatecfg(CT_All);
	timestamp = (time_t)get_timestamp(2024, (_i % 4 < 2) ? 1 : 7, 7, 18, 25);
	ck_assert_int_eq(db_open_rw(1), 1);
	ck_assert_int_eq(db_addinterface("billing0"), 1);
	ck_assert_int_eq(db_setupdated("billing0", timestamp), 1);
	ck_assert_int_eq(datacache_add(&state.dcache, "billing0", 0), 1);
	ck_assert_int_eq(initcachevalues(&state, &state.dcache), 1);
	ck_assert_int_eq(state.dcache->updated, timestamp);
	datacache_clear(&state.dcache);
	ck_assert_int_eq(db_close(), 1);
}
END_TEST

START_TEST(billing_cache_flush_respects_boundary)
{
	DSTATE state;
	dbdatalist *data = NULL;
	dbdatalistinfo info;
	time_t boundary;
	initdstate(&state);
	strcpy(cfg.dbdir, TESTDBDIR);
	cfg.monthrotate = 7;
	cfg.monthrotatehour = 18;
	cfg.monthrotateminute = 25;
	boundary = (time_t)get_timestamp(2024, 1, 7, 18, 25);
	ck_assert_int_eq(db_open_rw(1), 1);
	ck_assert_int_eq(db_addinterface("billing0"), 1);
	ck_assert_int_eq(datacache_add(&state.dcache, "billing0", 0), 1);
	state.dcache->updated = boundary + 300;
	state.dcache->currx = 40;
	state.dcache->curtx = 60;
	ck_assert_int_eq(xferlog_add(&state.dcache->log, boundary - 300, 10, 20), 1);
	ck_assert_int_eq(xferlog_add(&state.dcache->log, boundary, 30, 40), 1);
	flushcachetodisk(&state);
	ck_assert_int_eq(db_errcode, 0);
	ck_assert_ptr_eq(state.dcache->log, NULL);
	ck_assert_int_eq(db_getdata(&data, &info, "billing0", "month", 0), 1);
	ck_assert_int_eq(info.count, 2);
	ck_assert_int_eq(data->rx, 10);
	ck_assert_int_eq(data->next->rx, 30);
	dbdatalistfree(&data);
	datacache_clear(&state.dcache);
	ck_assert_int_eq(db_close(), 1);
}
END_TEST

START_TEST(billing_utc_ignores_local_dst_duration)
{
	struct tm labeltm;
	time_t label;
	setenv("TZ", "America/New_York", 1);
	tzset();
	cfg.useutc = 1;
	cfg.monthrotate = 7;
	cfg.monthrotatehour = 18;
	cfg.monthrotateminute = 25;
	memset(&labeltm, 0, sizeof(labeltm));
	labeltm.tm_year = 2024 - 1900;
	labeltm.tm_mon = 2;
	labeltm.tm_mday = 1;
	labeltm.tm_isdst = -1;
	label = mktime(&labeltm);
	ck_assert_int_eq(getperiodseconds(LT_Month, label, 0, 0, 0), 31 * 86400);
}
END_TEST

void add_billing_tests(Suite *s)
{
	TCase *tc = tcase_create("Billing");
	tcase_add_checked_fixture(tc, billing_fixture, teardown);
	tcase_add_test(tc, billing_config_validation);
	tcase_add_loop_test(tc, billing_minute_database_boundary, 0, 6);
	tcase_add_loop_test(tc, billing_minute_cache_separates_periods, 0, 6);
	tcase_add_loop_test(tc, billing_minute_straddling_sample_keeps_upstream_attribution, 0, 60);
	tcase_add_loop_test(tc, billing_database_boundary, 0, 6);
	tcase_add_test(tc, billing_first_day_nonmidnight);
	tcase_add_test(tc, billing_periods_and_estimates);
	tcase_add_test(tc, billing_direct_import_preserves_labels);
	tcase_add_loop_test(tc, billing_cache_uses_real_epoch, 0, 12);
	tcase_add_test(tc, billing_cache_flush_respects_boundary);
	tcase_add_test(tc, billing_utc_ignores_local_dst_duration);
	suite_add_tcase(s, tc);
}
