/*
 * Copyright (C) 2025 Red Hat, Inc.
 *
 * This program is free software; you can redistribute it and/or modify it
 * under the terms of the GNU Lesser General Public License as published by
 * the Free Software Foundation; either version 2.1 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful, but
 * WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
 * Lesser General Public License for more details.
 *
 * You should have received a copy of the GNU Lesser General Public License
 * along with This program; If not, see <http://www.gnu.org/licenses/>.
 */
import cockpit from "cockpit";

import { DateTime } from "luxon";

import React, { useEffect, useState } from "react";
import {
    Checkbox,
    Flex,
    FlexItem,
    FormGroup,
    MenuToggle,
    Select,
    SelectList,
    SelectOption,
    Stack,
    StackItem,
    Title,
} from "@patternfly/react-core";

import {
    getAllValidTimezones,
    getTimezone,
    setTimezone,
} from "../../apis/timezone.js";

const _ = cockpit.gettext;
const SCREEN_ID = "anaconda-screen-date-time";

export const TimezoneSection = ({ locale, setSectionValid, setTimezoneLabel }) => {
    const [autoTimezone, setAutoTimezone] = useState(true);
    const [regionSelectOpen, setRegionSelectOpen] = useState(false);
    const [citySelectOpen, setCitySelectOpen] = useState(false);
    const [regions, setRegions] = useState([]);
    const [citiesByRegion, setCitiesByRegion] = useState({});
    const [region, setRegion] = useState("");
    const [city, setCity] = useState("");
    const [shownTimezoneLabel, setShownTimezoneLabel] = useState("");

    useEffect(() => {
        getAllValidTimezones().then(zoneDict => {
            const keys = Object.keys(zoneDict || {});
            setRegions(keys);
            setCitiesByRegion(zoneDict || {});
            if (keys.length) {
                setRegion(keys[0]);
                setCity(zoneDict[keys[0]][0]);
            }
        });
        getTimezone().then(val => {
            if (val && typeof val === "string" && val.includes("/")) {
                const [reg, cty] = val.split("/");
                setRegion(reg);
                setCity(cty);
            }
        });
    }, []);

    useEffect(() => {
        setSectionValid(autoTimezone || (!!region && !!city));
    }, [autoTimezone, region, city, setSectionValid]);

    useEffect(() => {
        if (region && city) {
            const zone = `${region}/${city}`;
            const dt = DateTime.now().setZone(zone);
            const formatter = new Intl.DateTimeFormat(locale, {
                hour: "2-digit",
                minute: "2-digit",
                timeZone: zone,
                timeZoneName: "short"
            });

            const parts = formatter.formatToParts(new Date());
            const tzPart = parts.find(p => p.type === "timeZoneName");
            const abbreviation = tzPart?.value;

            const offsetHours = dt.offset / 60;
            const offsetStr = `UTC${offsetHours >= 0 ? "+" : ""}${offsetHours}`;

            const label = (abbreviation && !abbreviation.includes("/"))
                ? `${abbreviation}, ${offsetStr}`
                : offsetStr;

            setTimezoneLabel(zone);
            setShownTimezoneLabel(label);
        }
    }, [region, city, setTimezoneLabel, locale]);

    const handleRegionSelect = (_ev, value) => {
        setRegion(value);
        setCity(citiesByRegion[value][0]);
        setRegionSelectOpen(false);
        setTimezone({ timezone: `${value}/${citiesByRegion[value][0]}` });
    };
    const handleCitySelect = (_ev, value) => {
        setCity(value);
        setCitySelectOpen(false);
        setTimezone({ timezone: `${region}/${value}` });
    };

    const regionToggle = toggleRef => (
        <MenuToggle
          ref={toggleRef}
          id={`${SCREEN_ID}-region-toggle`}
          onClick={() => setRegionSelectOpen(!regionSelectOpen)}
          isExpanded={regionSelectOpen}
          isDisabled={autoTimezone}
          className={`${SCREEN_ID}__region-toggle`}
        >
            {region}
        </MenuToggle>
    );
    const cityToggle = toggleRef => (
        <MenuToggle
          ref={toggleRef}
          id={`${SCREEN_ID}-city-toggle`}
          onClick={() => setCitySelectOpen(!citySelectOpen)}
          isExpanded={citySelectOpen}
          isDisabled={autoTimezone}
          className={`${SCREEN_ID}__city-toggle`}
        >
            {city}
        </MenuToggle>
    );

    return (
        <>
            <Title headingLevel="h2">{_("Timezone")}</Title>
            <FormGroup>
                <Stack hasGutter>
                    <StackItem>
                        <Flex alignItems={{ default: "alignItemsCenter" }}>
                            <FlexItem>
                                <Checkbox
                                  id={`${SCREEN_ID}-auto-timezone`}
                                  isChecked={autoTimezone}
                                  onChange={() => setAutoTimezone(!autoTimezone)}
                                  label={_("Automatically set timezone")}
                                  aria-label={_("Automatically set timezone")}
                                />
                            </FlexItem>
                        </Flex>
                    </StackItem>
                    <StackItem>
                        <Flex alignItems={{ default: "alignItemsCenter" }} className={`${SCREEN_ID}__indent`}>
                            <FlexItem>
                                <Select
                                  id={`${SCREEN_ID}-region`}
                                  isOpen={regionSelectOpen}
                                  selected={region}
                                  onSelect={handleRegionSelect}
                                  onOpenChange={setRegionSelectOpen}
                                  toggle={regionToggle}
                                  shouldFocusToggleOnSelect
                                  aria-label={_("Select region")}
                                  className={`${SCREEN_ID}__select--region`}
                                >
                                    <SelectList className={`${SCREEN_ID}__select-list--scrollable`}>
                                        {regions.map(r =>
                                            <SelectOption key={r} value={r}>{r}</SelectOption>
                                        )}
                                    </SelectList>
                                </Select>
                            </FlexItem>
                            <FlexItem>
                                <Select
                                  id={`${SCREEN_ID}-city`}
                                  isOpen={citySelectOpen}
                                  selected={city}
                                  onSelect={handleCitySelect}
                                  onOpenChange={setCitySelectOpen}
                                  toggle={cityToggle}
                                  shouldFocusToggleOnSelect
                                  aria-label={_("Select city")}
                                  className={`${SCREEN_ID}__select--city`}
                                >
                                    <SelectList className={`${SCREEN_ID}__select-list--scrollable`}>
                                        {(citiesByRegion[region] || [])
                                                .sort((a, b) => a.localeCompare(b))
                                                .map(c =>
                                                    <SelectOption key={c} value={c}>{c}</SelectOption>
                                                )}
                                    </SelectList>
                                </Select>
                            </FlexItem>
                            <FlexItem>
                                <span className={`${SCREEN_ID}__timezone-label`}>
                                    {shownTimezoneLabel}
                                </span>
                            </FlexItem>
                        </Flex>
                    </StackItem>
                </Stack>
            </FormGroup>
        </>
    );
};
