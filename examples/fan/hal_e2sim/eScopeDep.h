/*
 * eScope dependencies - firmware simulated on e2Sim (MIT)
 *
 * The UART reception is polled from the main loop (eScopeTransport_Poll): no interrupt shares the eScope state,
 * the critical sections are empty.
 */
#ifndef ESCOPE_DEP_H_
#define ESCOPE_DEP_H_

#define CRITICAL_SECTION_ALLOC()
#define CRITICAL_SECTION_ENTER()
#define CRITICAL_SECTION_EXIT()

#endif /* ESCOPE_DEP_H_ */
