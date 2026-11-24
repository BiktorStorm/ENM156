import company 
import machine
import process
import privateSchedule
import areaSchedule

companyA = company.company(companyName="ABB")


svarv1 = machine.machine(50, "Supersvarv")
companyA.addMachine(svarv1)

svarv1_körning = process.process(svarv1, 15)

schema1 = privateSchedule.schedule()

schema1.addProcess(svarv1_körning, 3)



schemaOmråde = areaSchedule.schedule()

print(schema1.getTotalPowerAtIndex(2))


