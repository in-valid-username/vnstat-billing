#include "common.h"
#include "dbsql.h"
#include "percentile.h"

static time_t percentilegridcutoff(const time_t cutoff, const int roundup)
{
	struct tm calendar;
	int remainder;

	if ((cfg.useutc ? gmtime_r(&cutoff, &calendar) : localtime_r(&cutoff, &calendar)) == NULL) {
		return (time_t)-1;
	}
	if (calendar.tm_min % 5 == 0 && calendar.tm_sec == 0) {
		/* Preserve the helper's chosen DST instant for an already aligned cutoff. */
		return cutoff;
	}
	if (roundup && calendar.tm_sec != 0) {
		calendar.tm_min++;
	}
	remainder = calendar.tm_min % 5;
	calendar.tm_min += roundup ? (5 - remainder) % 5 : -remainder;
	calendar.tm_sec = 0;
	calendar.tm_isdst = -1;
	return cfg.useutc ? timegm(&calendar) : mktime(&calendar);
}

int getpercentiledata(percentiledata *pdata, const char *iface, const uint64_t userlimitbytespersecond)
{
	uint32_t entry = 0, entrylimit;
	uint64_t *rxdata, *txdata, *sumdata;
	const struct tm *d;
	struct tm calendar;
	time_t monthlabel, monthbegin, monthend, firstslot, lastslot;
	char datebuff[DATEBUFFLEN], dateend[DATEBUFFLEN];
	dbdatalist *datalist = NULL, *datalist_i = NULL;
	dbdatalistinfo datainfo;

	pdata->userlimitbytespersecond = userlimitbytespersecond;
	pdata->countrxoveruserlimit = 0;
	pdata->counttxoveruserlimit = 0;
	pdata->countsumoveruserlimit = 0;

	if (!db_getdata_range(&datalist, &datainfo, iface, "month", 1, "", "")) {
		snprintf(errorstring, 1024, "Failed to fetch month data for 95th percentile.");
		printe(PT_Error);
		return 0;
	}

	if (!datalist) {
		snprintf(errorstring, 1024, "No month data for 95th percentile available.");
		printe(PT_Error);
		return 0;
	}

	monthlabel = db_getmonthlabel(datalist->rowid);
	monthbegin = monthlabel == (time_t)-1 ? (time_t)-1 : billingperiodstart(monthlabel, 0, 0);
	monthend = monthlabel == (time_t)-1 ? (time_t)-1 : billingperiodstart(monthlabel, 0, 1);
	dbdatalistfree(&datalist);
	if (monthbegin == (time_t)-1 || monthend == (time_t)-1 || monthend <= monthbegin) {
		snprintf(errorstring, 1024, "Failed to determine billing period for 95th percentile.");
		printe(PT_Error);
		return 0;
	}
	d = cfg.useutc ? gmtime(&monthbegin) : localtime(&monthbegin);
	pdata->monthbegin = monthbegin;
	if (cfg.useutc) {
		/* Public dates retain the query-calendar contract. TZ=UTC avoids local DST gaps. */
		calendar = *d;
		calendar.tm_isdst = -1;
		pdata->monthbegin = mktime(&calendar);
	}
	/* Persisted buckets are indivisible: omit either bucket straddling a cutoff. */
	firstslot = percentilegridcutoff(monthbegin, 1);
	lastslot = percentilegridcutoff(monthend, 0);
	if (firstslot == (time_t)-1 || lastslot == (time_t)-1) {
		snprintf(errorstring, 1024, "Failed to determine billing period for 95th percentile.");
		printe(PT_Error);
		return 0;
	}
	/* The range API has an inclusive end and bucket dates denote their starts. */
	lastslot -= 300;
	if (lastslot < firstslot) {
		snprintf(errorstring, 1024, "No 5 minute data for 95th percentile available.");
		printe(PT_Error);
		return 0;
	}
	d = cfg.useutc ? gmtime(&firstslot) : localtime(&firstslot);
	strftime(datebuff, DATEBUFFLEN, "%Y-%m-%d %H:%M", d);
	d = cfg.useutc ? gmtime(&lastslot) : localtime(&lastslot);
	strftime(dateend, DATEBUFFLEN, "%Y-%m-%d %H:%M", d);

	if (!db_getdata_range(&datalist, &datainfo, iface, "fiveminute", 0, datebuff, dateend)) {
		snprintf(errorstring, 1024, "Failed to fetch 5 minute data for 95th percentile.");
		printe(PT_Error);
		return 0;
	}

	if (!datalist) {
		snprintf(errorstring, 1024, "No 5 minute data for 95th percentile available.");
		printe(PT_Error);
		return 0;
	}

	pdata->databegin = datainfo.mintime;
	pdata->dataend = datainfo.maxtime;
	pdata->count = datainfo.count;
	pdata->countexpectation = (uint32_t)((billingcalendartime(pdata->dataend) - firstslot) / 300 + 1);
	pdata->minrx = datainfo.minrx;
	pdata->mintx = datainfo.mintx;
	pdata->min = datainfo.min;
	pdata->sumrx = datainfo.sumrx;
	pdata->sumtx = datainfo.sumtx;
	pdata->maxrx = datainfo.maxrx;
	pdata->maxtx = datainfo.maxtx;
	pdata->max = datainfo.max;

	entrylimit = (uint32_t)lrint(datainfo.count * (double)0.95) - 1;

	if (debug) {
		printf("Entry expectation: %" PRIu32 "\n", pdata->countexpectation);
		printf("Entry count: %" PRIu32 "\n", pdata->count);
		printf("95th: %" PRIu32 "\n", entrylimit);
	}

	rxdata = (uint64_t *)malloc(datainfo.count * sizeof(uint64_t));
	txdata = (uint64_t *)malloc(datainfo.count * sizeof(uint64_t));
	sumdata = (uint64_t *)malloc(datainfo.count * sizeof(uint64_t));
	if (rxdata == NULL || txdata == NULL || sumdata == NULL) {
		panicexit(__FILE__, __LINE__);
	}

	datalist_i = datalist;
	while (datalist_i != NULL) {
		if (entry >= datainfo.count) {
			snprintf(errorstring, 1024, "Database query resulted in more data than expected (%" PRIu32 " >= %" PRIu32 ").", entry, datainfo.count);
			printe(PT_Error);
			free(rxdata);
			free(txdata);
			free(sumdata);
			dbdatalistfree(&datalist);
			return 0;
		}
		rxdata[entry] = datalist_i->rx;
		txdata[entry] = datalist_i->tx;
		sumdata[entry] = datalist_i->rx + datalist_i->tx;

		if (userlimitbytespersecond > 0) {
			if (rxdata[entry] > userlimitbytespersecond * 300) {
				pdata->countrxoveruserlimit++;
			}
			if (txdata[entry] > userlimitbytespersecond * 300) {
				pdata->counttxoveruserlimit++;
			}
			if (sumdata[entry] > userlimitbytespersecond * 300) {
				pdata->countsumoveruserlimit++;
			}
		}

		datalist_i = datalist_i->next;
		entry++;
	}

	if (datainfo.count != entry) {
		snprintf(errorstring, 1024, "Database query data count doesn't match entry count (%" PRIu32 " != %" PRIu32 ").", datainfo.count, entry);
		printe(PT_Error);
		free(rxdata);
		free(txdata);
		free(sumdata);
		dbdatalistfree(&datalist);
		return 0;
	}

	qsort((void *)rxdata, datainfo.count, sizeof(uint64_t), compare_uint64_t);
	qsort((void *)txdata, datainfo.count, sizeof(uint64_t), compare_uint64_t);
	qsort((void *)sumdata, datainfo.count, sizeof(uint64_t), compare_uint64_t);

	pdata->rxpercentile = rxdata[entrylimit];
	pdata->txpercentile = txdata[entrylimit];
	pdata->sumpercentile = sumdata[entrylimit];

	free(rxdata);
	free(txdata);
	free(sumdata);
	dbdatalistfree(&datalist);

	return 1;
}

int compare_uint64_t(const void *a, const void *b)
{
	if (*(const uint64_t *)a < *(const uint64_t *)b) {
		return -1;
	} else if (*(const uint64_t *)a > *(const uint64_t *)b) {
		return 1;
	}
	return 0;
}
